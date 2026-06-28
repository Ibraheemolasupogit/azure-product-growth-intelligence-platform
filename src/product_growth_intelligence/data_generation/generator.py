"""Deterministic NexaFlow synthetic data generator."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from random import Random

from product_growth_intelligence.data_generation.catalogues import (
    DEVICE_TYPES,
    EVENT_TAXONOMY,
    EVENTS_BY_FEATURE,
    EXPERIMENT_CATALOGUE,
    FEEDBACK_TEMPLATES,
    FEEDBACK_THEMES,
    OPERATING_SYSTEMS,
    PERSONA_BEHAVIOUR,
    PERSONAS,
    PLAN_CATALOGUE,
    REGIONS_BY_COUNTRY,
    TRAFFIC_SOURCES,
)
from product_growth_intelligence.data_generation.identifiers import stable_id
from product_growth_intelligence.data_generation.models import (
    GeneratedDatasets,
    GenerationConfig,
    JsonValue,
    Record,
)
from product_growth_intelligence.data_generation.profiles import validate_generation_config
from product_growth_intelligence.data_generation.validation import validate_datasets


def generate_datasets(config: GenerationConfig) -> GeneratedDatasets:
    """Generate and validate coherent synthetic datasets."""

    validate_generation_config(config)
    rng = Random(config.seed)
    users = _generate_users(config, rng)
    assignments = _generate_experiment_assignments(config, users, rng)
    subscriptions = _generate_subscriptions(config, users, assignments, rng)
    sessions, events = _generate_sessions_and_events(config, users, assignments, subscriptions, rng)
    feature_usage = _aggregate_feature_usage(events)
    feedback = _generate_feedback(config, users, events, rng)

    datasets = GeneratedDatasets(
        users=users,
        sessions=sessions,
        clickstream_events=events,
        feature_usage=feature_usage,
        subscriptions=subscriptions,
        experiment_assignments=assignments,
        customer_feedback=feedback,
    )
    validate_datasets(datasets)
    return datasets


def _generate_users(config: GenerationConfig, rng: Random) -> list[Record]:
    users: list[Record] = []
    start = datetime(
        config.start_date.year, config.start_date.month, config.start_date.day, tzinfo=UTC
    )
    span_days = max((config.end_date - config.start_date).days - 14, 1)

    for index in range(config.user_count):
        persona = (
            PERSONAS[index % len(PERSONAS)]
            if config.profile == "sample"
            else _weighted_choice(rng, config.persona_distribution)
        )
        country = _weighted_choice(rng, config.country_distribution)
        acquisition = _persona_acquisition_channel(persona, config, rng)
        behaviour = PERSONA_BEHAVIOUR[persona]
        signup = start + timedelta(days=rng.randrange(span_days), hours=rng.randrange(8, 21))
        initial_plan = (
            "starter" if persona in {"team_admin", "power_user"} and rng.random() < 0.20 else "free"
        )
        users.append(
            {
                "user_id": stable_id("usr", config.seed, index),
                "signup_timestamp": _iso(signup),
                "country": country,
                "region": REGIONS_BY_COUNTRY[str(country)],
                "acquisition_channel": acquisition,
                "device_preference": _weighted_choice(
                    rng, {"desktop": 0.68, "mobile": 0.22, "tablet": 0.10}
                ),
                "persona": persona,
                "company_size_band": behaviour["company_size"],
                "initial_plan": initial_plan,
                "marketing_consent": rng.random() < 0.72,
                "is_team_account": behaviour["company_size"] != "solo",
                "synthetic_record": True,
            }
        )
    return users


def _generate_experiment_assignments(
    config: GenerationConfig, users: list[Record], rng: Random
) -> list[Record]:
    assignments: list[Record] = []
    for user_index, user in enumerate(users):
        signup = _parse_timestamp(str(user["signup_timestamp"]))
        experiment_ids = list(EXPERIMENT_CATALOGUE)
        experiment_id = experiment_ids[user_index % len(experiment_ids)]
        variants = EXPERIMENT_CATALOGUE[experiment_id]["variants"]
        variant = variants[(user_index + rng.randrange(2)) % len(variants)]
        exposure = signup + timedelta(days=1 + rng.randrange(10), hours=rng.randrange(10))
        lift = EXPERIMENT_CATALOGUE[experiment_id]["base_conversion_lift"][variant]
        persona = str(user["persona"])
        converted = rng.random() < min(0.85, float(PERSONA_BEHAVIOUR[persona]["upgrade"]) + lift)
        conversion = exposure + timedelta(days=1 + rng.randrange(12)) if converted else None
        assignments.append(
            {
                "assignment_id": stable_id("asg", config.seed, user["user_id"], experiment_id),
                "experiment_id": experiment_id,
                "user_id": user["user_id"],
                "variant": variant,
                "assignment_timestamp": _iso(signup + timedelta(hours=2)),
                "eligibility_segment": EXPERIMENT_CATALOGUE[experiment_id]["eligibility"][0],
                "exposure_timestamp": _iso(exposure),
                "conversion_timestamp": _iso(conversion) if conversion else None,
                "converted": converted,
                "synthetic_record": True,
            }
        )
    return assignments


def _generate_subscriptions(
    config: GenerationConfig, users: list[Record], assignments: list[Record], rng: Random
) -> list[Record]:
    subscriptions: list[Record] = []
    converted_users = {
        assignment["user_id"] for assignment in assignments if assignment["converted"]
    }

    for index, user in enumerate(users):
        user_id = str(user["user_id"])
        signup = _parse_timestamp(str(user["signup_timestamp"]))
        period_start = signup
        initial_plan = str(user["initial_plan"])
        persona = str(user["persona"])
        churn_probability = float(PERSONA_BEHAVIOUR[persona]["churn"])

        if initial_plan != "free":
            paid_plan = initial_plan
            subscriptions.append(
                _subscription_record(
                    config, user_id, index, 0, paid_plan, "monthly", "active", period_start, None
                )
            )
            continue

        trial_start = period_start + timedelta(days=3)
        trial_end = trial_start + timedelta(days=14)
        converted = user_id in converted_users or (config.profile == "sample" and index == 1)
        cancelled = rng.random() < churn_probability or (config.profile == "sample" and index == 2)

        if not converted:
            status = "cancelled" if cancelled else "active"
            period_end = trial_start if cancelled else None
            reason = "low_usage" if cancelled else None
            subscriptions.append(
                _subscription_record(
                    config,
                    user_id,
                    index,
                    0,
                    "free",
                    "none",
                    status,
                    period_start,
                    period_end,
                    cancellation_reason=reason,
                )
            )
            continue

        subscriptions.append(
            _subscription_record(
                config, user_id, index, 0, "free", "none", "converted", period_start, trial_start
            )
        )
        subscriptions.append(
            _subscription_record(
                config,
                user_id,
                index,
                1,
                "starter",
                "monthly",
                "trial",
                trial_start,
                trial_end,
                trial_start=trial_start,
                trial_end=trial_end,
            )
        )
        paid_plan = _paid_plan_for_persona(persona)
        paid_end = trial_end + timedelta(days=30) if cancelled else None
        subscriptions.append(
            _subscription_record(
                config,
                user_id,
                index,
                2,
                paid_plan,
                "monthly",
                "cancelled" if cancelled else "active",
                trial_end,
                paid_end,
                trial_start=trial_start,
                trial_end=trial_end,
                cancellation_reason="budget_constraints" if cancelled else None,
            )
        )
        if paid_plan == "team" and not cancelled and rng.random() < 0.25:
            upgrade_start = trial_end + timedelta(days=20)
            subscriptions[-1]["period_end_timestamp"] = _iso(upgrade_start)
            subscriptions.append(
                _subscription_record(
                    config,
                    user_id,
                    index,
                    3,
                    "business",
                    "monthly",
                    "active",
                    upgrade_start,
                    None,
                    trial_start=trial_start,
                    trial_end=trial_end,
                )
            )
    return subscriptions


def _generate_sessions_and_events(
    config: GenerationConfig,
    users: list[Record],
    assignments: list[Record],
    subscriptions: list[Record],
    rng: Random,
) -> tuple[list[Record], list[Record]]:
    sessions: list[Record] = []
    events: list[Record] = []
    assignment_by_user = {assignment["user_id"]: assignment for assignment in assignments}
    plans_by_user = _active_plans_by_user(subscriptions)

    for user_index, user in enumerate(users):
        user_id = str(user["user_id"])
        persona = str(user["persona"])
        behaviour = PERSONA_BEHAVIOUR[persona]
        min_sessions, max_sessions = behaviour["sessions"]
        session_count = rng.randint(int(min_sessions), int(max_sessions))
        signup = _parse_timestamp(str(user["signup_timestamp"]))
        assignment = assignment_by_user[user_id]

        for session_index in range(session_count):
            session_id = stable_id("ses", config.seed, user_id, session_index)
            start = signup + timedelta(
                days=min(
                    session_index * 3 + rng.randrange(3), (config.end_date - config.start_date).days
                ),
                hours=rng.randrange(8, 20),
                minutes=rng.randrange(60),
            )
            duration = rng.randint(240, 3600)
            end = start + timedelta(seconds=duration)
            device = (
                str(user["device_preference"]) if rng.random() < 0.78 else rng.choice(DEVICE_TYPES)
            )
            session_events = _session_events(
                config,
                rng,
                user,
                session_id,
                session_index,
                start,
                end,
                assignment,
                plans_by_user[user_id],
            )
            events.extend(session_events)
            sessions.append(
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "session_start_timestamp": _iso(start),
                    "session_end_timestamp": _iso(end),
                    "device_type": device,
                    "operating_system": _operating_system_for_device(device, rng),
                    "traffic_source": rng.choice(TRAFFIC_SOURCES),
                    "country": user["country"],
                    "event_count": len(session_events),
                    "session_duration_seconds": duration,
                    "synthetic_record": True,
                }
            )
        if user_index == 0 and config.profile == "sample":
            events.append(
                _event_record(
                    config,
                    user,
                    stable_id("ses", config.seed, user_id, 0),
                    len(events),
                    _parse_timestamp(str(sessions[0]["session_start_timestamp"]))
                    + timedelta(seconds=30),
                    "account_created",
                    99,
                    {"channel": user["acquisition_channel"]},
                )
            )
            sessions[0]["event_count"] = int(sessions[0]["event_count"]) + 1
    events.sort(
        key=lambda record: (str(record["session_id"]), int(record["event_sequence_number"]))
    )
    return sessions, events


def _session_events(
    config: GenerationConfig,
    rng: Random,
    user: Record,
    session_id: str,
    session_index: int,
    start: datetime,
    end: datetime,
    assignment: Record,
    plans: set[str],
) -> list[Record]:
    persona = str(user["persona"])
    behaviour = PERSONA_BEHAVIOUR[persona]
    event_names = ["session_started"]
    if session_index == 0:
        event_names.extend(["onboarding_started", "onboarding_step_completed", "workspace_created"])
        if rng.random() < (0.72 if persona != "casual_explorer" else 0.44):
            event_names.append("onboarding_completed")
    if session_index == 1:
        event_names.append("template_selected")

    available_features: set[str] = set()
    for plan in plans:
        available_features.update(PLAN_CATALOGUE[plan]["features"])
    preferred = [
        feature for feature in behaviour["preferred_features"] if feature in available_features
    ]
    for _ in range(rng.randint(2, 6)):
        feature = rng.choice(preferred or ["dashboard", "tasks", "search"])
        event_names.append(rng.choice(EVENTS_BY_FEATURE[feature]))

    if rng.random() < float(behaviour["collaboration"]):
        event_names.append(rng.choice(EVENTS_BY_FEATURE["collaboration"]))
    if rng.random() < 0.20:
        event_names.extend(
            [
                "recommendation_shown",
                rng.choice(["recommendation_clicked", "recommendation_accepted"]),
            ]
        )
    if session_index == 1:
        event_names.append("upgrade_prompt_viewed")
    if assignment["converted"] and assignment["conversion_timestamp"] and session_index == 2:
        event_names.append("subscription_started")
    if rng.random() < (0.07 if persona != "power_user" else 0.11):
        event_names.append(rng.choice(["feature_error", "request_failed"]))

    total_seconds = max(int((end - start).total_seconds()), len(event_names) + 1)
    records: list[Record] = []
    for sequence, event_name in enumerate(event_names, start=1):
        offset_seconds = min(
            sequence * max(total_seconds // (len(event_names) + 1), 1),
            total_seconds - 1,
        )
        timestamp = start + timedelta(seconds=offset_seconds)
        experiment_id = None
        experiment_variant = None
        if event_name in {
            "onboarding_started",
            "template_selected",
            "upgrade_prompt_viewed",
            "automation_created",
        }:
            experiment_id = assignment["experiment_id"]
            experiment_variant = assignment["variant"]
        records.append(
            _event_record(
                config,
                user,
                session_id,
                sequence,
                timestamp,
                event_name,
                sequence,
                _properties_for_event(event_name, user, assignment, rng),
                experiment_id=experiment_id,
                experiment_variant=experiment_variant,
            )
        )
    return records


def _aggregate_feature_usage(events: list[Record]) -> list[Record]:
    grouped: dict[tuple[str, str, str], dict[str, int]] = defaultdict(
        lambda: {
            "usage_count": 0,
            "active_minutes": 0,
            "successful_action_count": 0,
            "error_count": 0,
        }
    )
    for event in events:
        feature = event["feature_name"]
        if feature is None:
            continue
        key = (str(event["user_id"]), str(feature), str(event["event_timestamp"])[:10])
        grouped[key]["usage_count"] += 1
        grouped[key]["active_minutes"] += 2
        event_type = EVENT_TAXONOMY[str(event["event_name"])].event_type
        if event_type == "success":
            grouped[key]["successful_action_count"] += 1
        if event_type == "failure":
            grouped[key]["error_count"] += 1

    records: list[Record] = []
    for (user_id, feature, observation_date), values in sorted(grouped.items()):
        records.append(
            {
                "usage_id": stable_id("usg", user_id, feature, observation_date),
                "user_id": user_id,
                "observation_date": observation_date,
                "feature_name": feature,
                "usage_count": values["usage_count"],
                "active_minutes": values["active_minutes"],
                "successful_action_count": values["successful_action_count"],
                "error_count": values["error_count"],
                "synthetic_record": True,
            }
        )
    return records


def _generate_feedback(
    config: GenerationConfig, users: list[Record], events: list[Record], rng: Random
) -> list[Record]:
    feedback: list[Record] = []
    events_by_user: dict[str, list[Record]] = defaultdict(list)
    errors_by_user: dict[str, int] = defaultdict(int)
    for event in events:
        user_id = str(event["user_id"])
        events_by_user[user_id].append(event)
        if EVENT_TAXONOMY[str(event["event_name"])].event_type == "failure":
            errors_by_user[user_id] += 1

    for index, user in enumerate(users):
        persona = str(user["persona"])
        probability = max(
            config.feedback_probability, float(PERSONA_BEHAVIOUR[persona]["feedback"])
        )
        if config.profile == "sample" and index < 3:
            should_feedback = True
        else:
            should_feedback = rng.random() < probability
        if not should_feedback:
            continue
        sentiment = _feedback_sentiment(index, errors_by_user[str(user["user_id"])], rng)
        user_events = events_by_user[str(user["user_id"])]
        anchor = user_events[-1] if user_events else None
        timestamp = (
            _parse_timestamp(str(anchor["event_timestamp"])) + timedelta(hours=2)
            if anchor
            else _parse_timestamp(str(user["signup_timestamp"])) + timedelta(days=5)
        )
        theme = (
            FEEDBACK_THEMES[index % len(FEEDBACK_THEMES)]
            if config.profile == "sample"
            else rng.choice(FEEDBACK_THEMES)
        )
        feature = anchor["feature_name"] if anchor and anchor["feature_name"] else "dashboard"
        feedback.append(
            {
                "feedback_id": stable_id("fbk", config.seed, user["user_id"], index),
                "user_id": user["user_id"],
                "feedback_timestamp": _iso(timestamp),
                "feedback_channel": rng.choice(("in_app", "survey", "support_ticket", "community")),
                "rating": {"positive": 5, "neutral": 3, "negative": 2}[sentiment],
                "feedback_text": FEEDBACK_TEMPLATES[sentiment][
                    index % len(FEEDBACK_TEMPLATES[sentiment])
                ],
                "feedback_theme": theme,
                "feature_name": feature,
                "synthetic_sentiment_label": sentiment,
                "synthetic_record": True,
            }
        )
    return feedback


def _event_record(
    config: GenerationConfig,
    user: Record,
    session_id: str,
    global_index: int,
    timestamp: datetime,
    event_name: str,
    sequence_number: int,
    properties: dict[str, JsonValue],
    experiment_id: object | None = None,
    experiment_variant: object | None = None,
) -> Record:
    spec = EVENT_TAXONOMY[event_name]
    recommendation_id = (
        stable_id("rec", user["user_id"], timestamp.date())
        if event_name.startswith("recommendation_")
        else None
    )
    return {
        "event_id": stable_id(
            "evt", config.seed, user["user_id"], session_id, global_index, event_name
        ),
        "session_id": session_id,
        "user_id": user["user_id"],
        "event_timestamp": _iso(timestamp),
        "event_name": event_name,
        "feature_name": spec.feature_name,
        "page_name": _page_for_stage(spec.journey_stage),
        "journey_stage": spec.journey_stage,
        "device_type": user["device_preference"],
        "event_sequence_number": sequence_number,
        "experiment_id": experiment_id,
        "experiment_variant": experiment_variant,
        "recommendation_id": recommendation_id,
        "properties": properties,
        "synthetic_record": True,
    }


def _subscription_record(
    config: GenerationConfig,
    user_id: str,
    user_index: int,
    period_index: int,
    plan_name: str,
    billing_cycle: str,
    status: str,
    period_start: datetime,
    period_end: datetime | None,
    trial_start: datetime | None = None,
    trial_end: datetime | None = None,
    cancellation_reason: str | None = None,
) -> Record:
    return {
        "subscription_id": stable_id("sub", config.seed, user_id, period_index),
        "user_id": user_id,
        "plan_name": plan_name,
        "billing_cycle": billing_cycle,
        "status": status,
        "period_start_timestamp": _iso(period_start),
        "period_end_timestamp": _iso(period_end) if period_end else None,
        "trial_start_timestamp": _iso(trial_start) if trial_start else None,
        "trial_end_timestamp": _iso(trial_end) if trial_end else None,
        "monthly_recurring_revenue": PLAN_CATALOGUE[plan_name]["monthly_recurring_revenue"],
        "cancellation_reason": cancellation_reason,
        "synthetic_record": True,
    }


def _weighted_choice(rng: Random, distribution: dict[str, float]) -> str:
    marker = rng.random()
    cumulative = 0.0
    for value, probability in distribution.items():
        cumulative += probability
        if marker <= cumulative:
            return value
    return next(reversed(distribution))


def _persona_acquisition_channel(persona: str, config: GenerationConfig, rng: Random) -> str:
    if persona in {"team_admin", "operations_lead"} and rng.random() < 0.45:
        return rng.choice(("partner_referral", "app_marketplace"))
    if persona == "power_user" and rng.random() < 0.40:
        return "product_led_referral"
    return _weighted_choice(rng, config.acquisition_channel_distribution)


def _paid_plan_for_persona(persona: str) -> str:
    if persona in {"team_admin", "operations_lead"}:
        return "team"
    if persona == "power_user":
        return "business"
    return "starter"


def _active_plans_by_user(subscriptions: list[Record]) -> dict[str, set[str]]:
    plans: dict[str, set[str]] = defaultdict(set)
    for subscription in subscriptions:
        plans[str(subscription["user_id"])].add(str(subscription["plan_name"]))
    return plans


def _operating_system_for_device(device: str, rng: Random) -> str:
    if device == "mobile":
        return rng.choice(("iOS", "Android"))
    if device == "tablet":
        return rng.choice(("iOS", "Android"))
    return rng.choice(OPERATING_SYSTEMS)


def _properties_for_event(
    event_name: str, user: Record, assignment: Record, rng: Random
) -> dict[str, JsonValue]:
    if event_name == "account_created":
        return {"channel": str(user["acquisition_channel"])}
    if event_name == "onboarding_step_completed":
        return {"step": rng.choice(("profile", "workspace", "first_project"))}
    if event_name == "search_performed":
        return {"query_type": rng.choice(("task", "project", "file"))}
    if event_name == "integration_connected":
        return {"integration_type": rng.choice(("calendar", "storage", "chat"))}
    if event_name == "upgrade_prompt_viewed":
        return {"prompt": str(assignment["experiment_id"])}
    if event_name in {"subscription_started", "plan_upgraded", "plan_downgraded"}:
        return {"plan_name": _paid_plan_for_persona(str(user["persona"]))}
    if event_name == "subscription_cancelled":
        return {"reason": "budget_constraints"}
    if event_name.startswith("recommendation_"):
        return {"surface": rng.choice(("dashboard", "project_sidebar", "onboarding"))}
    if event_name == "feature_error":
        return {"error_code": rng.choice(("timeout", "validation_error", "upload_failed"))}
    if event_name == "request_failed":
        return {"status_code": rng.choice((429, 500, 503))}
    return {}


def _page_for_stage(stage: str) -> str:
    return {
        "acquisition": "signup",
        "onboarding": "onboarding",
        "activation": "workspace",
        "engagement": "workspace",
        "collaboration": "project",
        "advanced": "settings",
        "monetisation": "billing",
        "retention": "billing",
        "recommendation": "dashboard",
        "reliability": "workspace",
    }[stage]


def _feedback_sentiment(index: int, error_count: int, rng: Random) -> str:
    if index == 0:
        return "positive"
    if index == 1:
        return "neutral"
    if index == 2:
        return "negative"
    if error_count > 0 and rng.random() < 0.70:
        return "negative"
    return rng.choice(("positive", "positive", "neutral", "negative"))


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
