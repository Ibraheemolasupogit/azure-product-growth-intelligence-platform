"""Cohort assignment and period activity construction."""

from __future__ import annotations

from collections import Counter, defaultdict

from product_growth_intelligence.analytics.funnel_definitions import default_funnel_definitions
from product_growth_intelligence.analytics.funnel_models import TrustedInput
from product_growth_intelligence.analytics.journey import reconstruct_attempts
from product_growth_intelligence.analytics.retention.models import (
    CohortMembership,
    RetentionDefinition,
    UserPeriodActivity,
)
from product_growth_intelligence.analytics.retention.periods import (
    add_periods,
    iso,
    parse_timestamp,
    period_label,
    period_start,
)
from product_growth_intelligence.data_generation.models import JsonValue, Record
from product_growth_intelligence.ingestion.fingerprints import record_fingerprint

PAID_PLANS = frozenset({"starter", "team", "business"})
COLLABORATION_EVENTS = frozenset(
    {"invite_sent", "invite_accepted", "member_added", "project_shared", "comment_added"}
)
AUTOMATION_EVENTS = frozenset({"automation_executed"})
RECOMMENDATION_EVENTS = frozenset({"recommendation_clicked", "recommendation_accepted"})
ACTIVATION_EVENTS = frozenset({"task_completed", "workspace_created"})


def build_memberships(
    trusted: TrustedInput,
    definitions: tuple[RetentionDefinition, ...],
    analysis_start: str,
    analysis_end: str,
) -> list[CohortMembership]:
    """Assign one cohort membership per user per definition."""

    users = {str(row["user_id"]): row for row in trusted.datasets["users"]}
    events_by_user = _events_by_user(trusted.datasets["clickstream_events"])
    subscriptions_by_user = _records_by_user(trusted.datasets["subscriptions"])
    assignments_by_user = _records_by_user(trusted.datasets["experiment_assignments"])
    start = parse_timestamp(analysis_start)
    end = parse_timestamp(analysis_end)
    funnel_attempts, _, _ = reconstruct_attempts(
        trusted, default_funnel_definitions(), analysis_start, analysis_end
    )
    activated_users = {
        attempt.user_id
        for attempt in funnel_attempts
        if attempt.funnel_id == "account_activation" and attempt.attempt_status == "completed"
    }
    memberships: list[CohortMembership] = []

    for definition in definitions:
        for user_id, user in sorted(users.items()):
            anchor = _anchor_for(
                definition, user, events_by_user[user_id], subscriptions_by_user[user_id]
            )
            if anchor is None or not start <= parse_timestamp(anchor) <= end:
                continue
            segments = _segments(
                user,
                events_by_user[user_id],
                subscriptions_by_user[user_id],
                assignments_by_user[user_id],
                activated=user_id in activated_users
                or _has_event(events_by_user[user_id], ACTIVATION_EVENTS),
            )
            memberships.append(
                CohortMembership(
                    membership_id=_membership_id(
                        definition.definition_id, definition.version, user_id, anchor
                    ),
                    definition_id=definition.definition_id,
                    definition_version=definition.version,
                    user_id=user_id,
                    anchor_timestamp=anchor,
                    cohort_period=period_label(parse_timestamp(anchor), definition.time_grain),
                    segments=segments,
                    source_ingestion_run_id=trusted.source_ingestion_run_id,
                )
            )
    return sorted(
        memberships, key=lambda item: (item.definition_id, item.cohort_period, item.user_id)
    )


def build_user_period_activity(
    trusted: TrustedInput,
    definitions: tuple[RetentionDefinition, ...],
    memberships: list[CohortMembership],
    analysis_end: str,
) -> list[UserPeriodActivity]:
    """Build one period row per membership and horizon index."""

    definitions_by_id = {definition.definition_id: definition for definition in definitions}
    events_by_user = _events_by_user(trusted.datasets["clickstream_events"])
    end = parse_timestamp(analysis_end)
    rows: list[UserPeriodActivity] = []
    for membership in memberships:
        definition = definitions_by_id[membership.definition_id]
        anchor = parse_timestamp(membership.anchor_timestamp)
        anchor_period = period_start(anchor, definition.time_grain)
        for index in range(definition.maximum_horizon + 1):
            start = add_periods(anchor_period, index, definition.time_grain)
            period_end = add_periods(anchor_period, index + 1, definition.time_grain)
            observed = period_end <= end
            period_events = [
                event
                for event in events_by_user[membership.user_id]
                if start <= parse_timestamp(str(event["event_timestamp"])) < period_end
                and str(event["event_name"]) in definition.activity_rule.event_names
            ]
            active_days = len({str(event["event_timestamp"])[:10] for event in period_events})
            active = (
                observed
                and len(period_events) >= definition.activity_rule.minimum_event_count
                and active_days >= definition.activity_rule.minimum_active_days
            )
            rows.append(
                UserPeriodActivity(
                    membership_id=membership.membership_id,
                    definition_id=membership.definition_id,
                    user_id=membership.user_id,
                    cohort_period=membership.cohort_period,
                    period_index=index,
                    period_start=iso(start),
                    period_end=iso(period_end),
                    observed=observed,
                    active=active,
                    qualifying_event_count=len(period_events),
                    active_days=active_days,
                )
            )
    return rows


def _anchor_for(
    definition: RetentionDefinition,
    user: Record,
    events: list[Record],
    subscriptions: list[Record],
) -> str | None:
    if definition.anchor_rule == "signup_timestamp":
        return str(user["signup_timestamp"])
    if definition.anchor_rule == "first_task_completed_or_workspace_created":
        return _first_event_timestamp(events, ACTIVATION_EVENTS)
    if definition.anchor_rule == "first_paid_subscription_start":
        paid = [
            str(row["period_start_timestamp"])
            for row in subscriptions
            if str(row.get("plan_name")) in PAID_PLANS
        ]
        return min(paid) if paid else None
    if definition.anchor_rule == "first_collaboration_action":
        return _first_event_timestamp(events, COLLABORATION_EVENTS)
    if definition.anchor_rule == "first_automation_executed":
        return _first_event_timestamp(events, AUTOMATION_EVENTS)
    if definition.anchor_rule == "first_recommendation_click_or_accept":
        return _first_event_timestamp(events, RECOMMENDATION_EVENTS)
    return None


def _segments(
    user: Record,
    events: list[Record],
    subscriptions: list[Record],
    assignments: list[Record],
    *,
    activated: bool,
) -> dict[str, JsonValue]:
    current_plan = _current_plan(subscriptions) or str(user["initial_plan"])
    variant = str(assignments[0]["variant"]) if assignments else None
    return {
        "acquisition_channel": str(user["acquisition_channel"]),
        "persona": str(user["persona"]),
        "country": str(user["country"]),
        "region": str(user["region"]),
        "device_preference": str(user["device_preference"]),
        "actual_primary_device": _primary_device(events) or str(user["device_preference"]),
        "initial_plan": str(user["initial_plan"]),
        "current_plan": current_plan,
        "company_size_band": str(user["company_size_band"]),
        "is_team_account": bool(user["is_team_account"]),
        "activated": activated,
        "collaboration_adopter": _has_event(events, COLLABORATION_EVENTS),
        "automation_adopter": _has_event(events, AUTOMATION_EVENTS),
        "recommendation_engaged": _has_event(events, RECOMMENDATION_EVENTS),
        "paid_user": current_plan in PAID_PLANS,
        "experiment_variant": variant,
    }


def _events_by_user(events: list[Record]) -> dict[str, list[Record]]:
    grouped: dict[str, list[Record]] = defaultdict(list)
    for event in events:
        grouped[str(event["user_id"])].append(event)
    for records in grouped.values():
        records.sort(
            key=lambda event: (
                parse_timestamp(str(event["event_timestamp"])),
                str(event["session_id"]),
                int(event["event_sequence_number"]),
                str(event["event_id"]),
            )
        )
    return grouped


def _records_by_user(records: list[Record]) -> dict[str, list[Record]]:
    grouped: dict[str, list[Record]] = defaultdict(list)
    for record in records:
        grouped[str(record["user_id"])].append(record)
    return grouped


def _first_event_timestamp(events: list[Record], names: frozenset[str]) -> str | None:
    matches = [
        str(event["event_timestamp"]) for event in events if str(event["event_name"]) in names
    ]
    return min(matches) if matches else None


def _has_event(events: list[Record], names: frozenset[str]) -> bool:
    return any(str(event["event_name"]) in names for event in events)


def _current_plan(subscriptions: list[Record]) -> str | None:
    if not subscriptions:
        return None
    return str(
        sorted(subscriptions, key=lambda row: str(row["period_start_timestamp"]))[-1]["plan_name"]
    )


def _primary_device(events: list[Record]) -> str | None:
    counts = Counter(str(event["device_type"]) for event in events)
    if not counts:
        return None
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _membership_id(definition_id: str, version: str, user_id: str, anchor: str) -> str:
    return (
        "ret_"
        + record_fingerprint(
            {"definition": definition_id, "version": version, "user": user_id, "anchor": anchor}
        )[:20]
    )
