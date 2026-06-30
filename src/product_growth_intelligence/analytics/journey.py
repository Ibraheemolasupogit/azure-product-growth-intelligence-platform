"""Journey reconstruction and first-entry funnel attempts."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta

from product_growth_intelligence.analytics.funnel_models import (
    FunnelAttempt,
    FunnelDefinition,
    FunnelStage,
    StageMatch,
    TrustedInput,
)
from product_growth_intelligence.data_generation.models import JsonValue, Record
from product_growth_intelligence.ingestion.fingerprints import record_fingerprint

TEAM_PERSONAS = frozenset({"small_team_member", "team_admin", "operations_lead", "power_user"})
AUTOMATION_PLANS = frozenset({"business"})
PAID_PLANS = frozenset({"starter", "team", "business"})
ERROR_EVENTS = frozenset({"feature_error", "request_failed"})


def reconstruct_attempts(
    trusted: TrustedInput,
    definitions: tuple[FunnelDefinition, ...],
    analysis_start: str,
    analysis_end: str,
) -> tuple[list[FunnelAttempt], dict[str, int], list[str]]:
    """Build first-entry attempts for every enabled funnel."""

    users = {str(record["user_id"]): record for record in trusted.datasets["users"]}
    events_by_user = _events_by_user(trusted.datasets["clickstream_events"])
    sessions_by_id = {str(record["session_id"]): record for record in trusted.datasets["sessions"]}
    subscriptions_by_user = _records_by_user(trusted.datasets["subscriptions"])
    assignments_by_user = _records_by_user(trusted.datasets["experiment_assignments"])
    start = _parse(analysis_start)
    end = _parse(analysis_end)
    attempts: list[FunnelAttempt] = []
    eligible_counts: dict[str, int] = {}
    warnings: list[str] = []

    for definition in definitions:
        eligible_users = [
            user
            for user in users.values()
            if _is_eligible(
                definition,
                user,
                events_by_user.get(str(user["user_id"]), []),
                subscriptions_by_user.get(str(user["user_id"]), []),
                start,
                end,
            )
        ]
        eligible_counts[definition.funnel_id] = len(eligible_users)
        for user in sorted(eligible_users, key=lambda item: str(item["user_id"])):
            user_id = str(user["user_id"])
            attempt = _attempt_for_user(
                definition=definition,
                user=user,
                events=events_by_user.get(user_id, []),
                sessions_by_id=sessions_by_id,
                subscriptions=subscriptions_by_user.get(user_id, []),
                assignments=assignments_by_user.get(user_id, []),
                analysis_end=end,
                source_ingestion_run_id=trusted.source_ingestion_run_id,
            )
            if attempt is not None:
                attempts.append(attempt)
    return (
        sorted(attempts, key=lambda item: (item.funnel_id, item.user_id)),
        eligible_counts,
        warnings,
    )


def _attempt_for_user(
    *,
    definition: FunnelDefinition,
    user: Record,
    events: list[Record],
    sessions_by_id: dict[str, Record],
    subscriptions: list[Record],
    assignments: list[Record],
    analysis_end: datetime,
    source_ingestion_run_id: str,
) -> FunnelAttempt | None:
    stage_matches: dict[str, StageMatch] = {}
    stage_event_ids: dict[str, str] = {}
    stage_sessions: dict[str, str | None] = {}
    stage_timestamps: dict[str, str] = {}
    repeated_counts: dict[str, int] = {}
    cursor: datetime | None = None

    for index, stage in enumerate(definition.stages):
        match, count = _find_stage_match(stage, events, subscriptions, cursor)
        if match is None:
            break
        if index == 0:
            cursor = _parse(match.timestamp) - timedelta(microseconds=1)
        stage_matches[stage.stage_id] = match
        stage_event_ids[stage.stage_id] = match.event_id
        stage_sessions[stage.stage_id] = match.session_id
        stage_timestamps[stage.stage_id] = match.timestamp
        repeated_counts[stage.stage_id] = count
        cursor = _parse(match.timestamp)

    if not stage_matches or definition.entry_stage.stage_id not in stage_matches:
        return None

    entry = stage_matches[definition.entry_stage.stage_id]
    completion = stage_matches.get(definition.final_stage.stage_id)
    entry_time = _parse(entry.timestamp)
    completion_deadline = entry_time + timedelta(days=definition.allowed_completion_days)
    completed = completion is not None and _parse(completion.timestamp) <= completion_deadline
    highest = len(stage_matches) - 1
    if completed:
        assert completion is not None
        status = "completed"
        completion_timestamp = completion.timestamp
    elif completion_deadline > analysis_end:
        status = "censored"
        completion_timestamp = None
    elif highest == 0:
        status = "incomplete"
        completion_timestamp = None
    else:
        status = "abandoned"
        completion_timestamp = None

    last_observed_timestamp = _last_observed(events, subscriptions, entry.timestamp)
    exit_time = completion_timestamp or last_observed_timestamp
    attempt_id = _attempt_id(
        definition.funnel_id, definition.version, str(user["user_id"]), entry.timestamp
    )
    sessions_involved = len(
        {session_id for session_id in stage_sessions.values() if session_id is not None}
    )
    if sessions_involved == 0:
        sessions_involved = _sessions_between(events, entry.timestamp, exit_time)
    return FunnelAttempt(
        attempt_id=attempt_id,
        funnel_id=definition.funnel_id,
        funnel_version=definition.version,
        user_id=str(user["user_id"]),
        entry_timestamp=entry.timestamp,
        last_observed_timestamp=last_observed_timestamp,
        completion_timestamp=completion_timestamp,
        attempt_status=status,  # type: ignore[arg-type]
        highest_stage_reached=highest,
        stages_reached=tuple(stage.stage_id for stage in definition.stages[: highest + 1]),
        stage_timestamps=stage_timestamps,
        stage_event_ids=stage_event_ids,
        stage_session_ids=stage_sessions,
        sessions_involved=sessions_involved,
        repeated_event_counts=repeated_counts,
        error_events_before_exit=_error_events_between(events, entry.timestamp, exit_time),
        segments=_segments(user, events, subscriptions, assignments, sessions_by_id),
        source_ingestion_run_id=source_ingestion_run_id,
    )


def _find_stage_match(
    stage: FunnelStage,
    events: list[Record],
    subscriptions: list[Record],
    after: datetime | None,
) -> tuple[StageMatch | None, int]:
    matches: list[StageMatch] = []
    for event in events:
        timestamp = _parse(str(event["event_timestamp"]))
        if after is not None and timestamp <= after:
            continue
        if str(event["event_name"]) in stage.event_names:
            matches.append(
                StageMatch(
                    timestamp=str(event["event_timestamp"]),
                    event_id=str(event["event_id"]),
                    session_id=str(event["session_id"]),
                )
            )
    if stage.subscription_paid_outcome:
        for subscription in subscriptions:
            if str(subscription.get("plan_name")) in PAID_PLANS and str(
                subscription.get("status")
            ) in {
                "active",
                "trial",
                "cancelled",
            }:
                subscription_timestamp = str(subscription["period_start_timestamp"])
                if after is None or _parse(subscription_timestamp) > after:
                    matches.append(
                        StageMatch(
                            timestamp=subscription_timestamp,
                            event_id=f"subscription:{subscription['subscription_id']}",
                            session_id=None,
                        )
                    )
    matches = sorted(matches, key=lambda item: (_parse(item.timestamp), item.event_id))
    if len(matches) < stage.minimum_event_count:
        return None, len(matches)
    return matches[stage.minimum_event_count - 1], len(matches)


def _is_eligible(
    definition: FunnelDefinition,
    user: Record,
    events: list[Record],
    subscriptions: list[Record],
    start: datetime,
    end: datetime,
) -> bool:
    if definition.funnel_id == "account_activation":
        signup = _parse(str(user["signup_timestamp"]))
        return start <= signup <= end
    event_names = {str(event["event_name"]) for event in events}
    if definition.funnel_id == "onboarding":
        return "onboarding_started" in event_names
    if definition.funnel_id == "collaboration_adoption":
        return bool(user["is_team_account"]) or str(user["persona"]) in TEAM_PERSONAS
    if definition.funnel_id == "trial_to_paid":
        return "upgrade_prompt_viewed" in event_names or any(
            str(row.get("plan_name")) in PAID_PLANS for row in subscriptions
        )
    if definition.funnel_id == "automation_adoption":
        return "automation_created" in event_names or any(
            str(row.get("plan_name")) in AUTOMATION_PLANS for row in subscriptions
        )
    if definition.funnel_id == "recommendation_interaction":
        return "recommendation_shown" in event_names
    return False


def _segments(
    user: Record,
    events: list[Record],
    subscriptions: list[Record],
    assignments: list[Record],
    sessions_by_id: dict[str, Record],
) -> dict[str, JsonValue]:
    current_plan = _current_plan(subscriptions) or str(user["initial_plan"])
    actual_device = _actual_device(events, sessions_by_id) or str(user["device_preference"])
    variant = str(assignments[0]["variant"]) if assignments else None
    return {
        "persona": str(user["persona"]),
        "acquisition_channel": str(user["acquisition_channel"]),
        "country": str(user["country"]),
        "region": str(user["region"]),
        "device_preference": str(user["device_preference"]),
        "actual_session_device": actual_device,
        "initial_plan": str(user["initial_plan"]),
        "current_plan": current_plan,
        "company_size_band": str(user["company_size_band"]),
        "is_team_account": bool(user["is_team_account"]),
        "experiment_variant": variant,
    }


def _events_by_user(events: list[Record]) -> dict[str, list[Record]]:
    grouped: dict[str, list[Record]] = defaultdict(list)
    for event in events:
        grouped[str(event["user_id"])].append(event)
    for records in grouped.values():
        records.sort(
            key=lambda event: (
                _parse(str(event["event_timestamp"])),
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


def _last_observed(events: list[Record], subscriptions: list[Record], default: str) -> str:
    timestamps = [str(event["event_timestamp"]) for event in events]
    timestamps.extend(str(row["period_start_timestamp"]) for row in subscriptions)
    return max(timestamps, default=default)


def _sessions_between(events: list[Record], start: str, end: str) -> int:
    start_time = _parse(start)
    end_time = _parse(end)
    return len(
        {
            str(event["session_id"])
            for event in events
            if start_time <= _parse(str(event["event_timestamp"])) <= end_time
        }
    )


def _error_events_between(events: list[Record], start: str, end: str) -> int:
    start_time = _parse(start)
    end_time = _parse(end)
    return sum(
        1
        for event in events
        if str(event["event_name"]) in ERROR_EVENTS
        and start_time <= _parse(str(event["event_timestamp"])) <= end_time
    )


def _current_plan(subscriptions: list[Record]) -> str | None:
    if not subscriptions:
        return None
    ordered = sorted(subscriptions, key=lambda row: str(row["period_start_timestamp"]))
    return str(ordered[-1]["plan_name"])


def _actual_device(events: list[Record], sessions_by_id: dict[str, Record]) -> str | None:
    devices = Counter(
        str(sessions_by_id[str(event["session_id"])]["device_type"])
        for event in events
        if str(event["session_id"]) in sessions_by_id
    )
    if not devices:
        return None
    return sorted(devices.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _attempt_id(funnel_id: str, version: str, user_id: str, entry_timestamp: str) -> str:
    fingerprint = record_fingerprint(
        {"funnel": funnel_id, "version": version, "user": user_id, "entry": entry_timestamp}
    )
    return f"fna_{fingerprint[:20]}"


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
