"""Cross-dataset reconciliation rules for accepted ingestion records."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime

from product_growth_intelligence.data_generation.catalogues import EVENT_TAXONOMY
from product_growth_intelligence.data_generation.models import Record
from product_growth_intelligence.validation.rule_models import (
    RuleResult,
    SourceLocation,
    failed_rule,
)


def validate_cross_dataset(datasets: dict[str, list[Record]]) -> list[RuleResult]:
    """Validate referential, temporal, and aggregate integrity."""

    rules: list[RuleResult] = []
    user_ids = {str(row["user_id"]) for row in datasets.get("users", [])}
    session_ids = {str(row["session_id"]) for row in datasets.get("sessions", [])}
    rules.extend(_foreign_keys(datasets, user_ids, session_ids))
    rules.extend(_session_temporal_rules(datasets))
    rules.extend(_event_temporal_rules(datasets))
    rules.extend(_subscription_rules(datasets))
    rules.extend(_assignment_rules(datasets))
    rules.extend(_feedback_rules(datasets))
    rules.extend(_event_count_rules(datasets))
    rules.extend(_feature_usage_rules(datasets))
    return rules


def _foreign_keys(
    datasets: dict[str, list[Record]], user_ids: set[str], session_ids: set[str]
) -> list[RuleResult]:
    rules: list[RuleResult] = []
    for dataset, records in datasets.items():
        if dataset != "users":
            for record in records:
                if "user_id" in record and str(record["user_id"]) not in user_ids:
                    rules.append(_cross_failure(dataset, record, "FK_USER_MISSING", "user_id"))
        if dataset == "clickstream_events":
            for record in records:
                if str(record["session_id"]) not in session_ids:
                    rules.append(
                        _cross_failure(dataset, record, "FK_SESSION_MISSING", "session_id")
                    )
    return rules


def _session_temporal_rules(datasets: dict[str, list[Record]]) -> list[RuleResult]:
    signup_by_user = {
        str(row["user_id"]): _parse(str(row["signup_timestamp"]))
        for row in datasets.get("users", [])
    }
    rules: list[RuleResult] = []
    for session in datasets.get("sessions", []):
        start = _parse(str(session["session_start_timestamp"]))
        end = _parse(str(session["session_end_timestamp"]))
        if end < start:
            rules.append(
                _cross_failure(
                    "sessions", session, "SESSION_END_BEFORE_START", "session_end_timestamp"
                )
            )
        signup = signup_by_user.get(str(session["user_id"]))
        if signup and signup > start:
            rules.append(
                _cross_failure(
                    "sessions", session, "SIGNUP_AFTER_ACTIVITY", "session_start_timestamp"
                )
            )
    return rules


def _event_temporal_rules(datasets: dict[str, list[Record]]) -> list[RuleResult]:
    sessions = {str(row["session_id"]): row for row in datasets.get("sessions", [])}
    rules: list[RuleResult] = []
    sequences: dict[str, list[int]] = defaultdict(list)
    for event in datasets.get("clickstream_events", []):
        session = sessions.get(str(event["session_id"]))
        if session:
            timestamp = _parse(str(event["event_timestamp"]))
            start = _parse(str(session["session_start_timestamp"]))
            end = _parse(str(session["session_end_timestamp"]))
            if not start <= timestamp <= end:
                rules.append(
                    _cross_failure(
                        "clickstream_events",
                        event,
                        "EVENT_OUTSIDE_SESSION",
                        "event_timestamp",
                    )
                )
        sequences[str(event["session_id"])].append(int(event["event_sequence_number"]))
    for session_id, values in sequences.items():
        if values != sorted(values) or len(values) != len(set(values)):
            rules.append(
                failed_rule(
                    "EVENT_SEQUENCE_INVALID",
                    "Event sequence numbers increase inside sessions",
                    "error",
                    "temporal_integrity",
                    "clickstream_events",
                    f"Event sequence numbers are invalid for session {session_id}.",
                    field_name="event_sequence_number",
                )
            )
    return rules


def _subscription_rules(datasets: dict[str, list[Record]]) -> list[RuleResult]:
    rules: list[RuleResult] = []
    by_user: dict[str, list[Record]] = defaultdict(list)
    for record in datasets.get("subscriptions", []):
        start = _parse(str(record["period_start_timestamp"]))
        end_value = record.get("period_end_timestamp")
        if isinstance(end_value, str) and _parse(end_value) < start:
            rules.append(
                _cross_failure(
                    "subscriptions", record, "SUBSCRIPTION_END_BEFORE_START", "period_end_timestamp"
                )
            )
        by_user[str(record["user_id"])].append(record)
    for user_id, records in by_user.items():
        ordered = sorted(records, key=lambda item: str(item["period_start_timestamp"]))
        for current, next_record in zip(ordered, ordered[1:], strict=False):
            end_value = current.get("period_end_timestamp")
            if end_value is None or str(end_value) > str(next_record["period_start_timestamp"]):
                rules.append(
                    failed_rule(
                        "SUBSCRIPTION_PERIOD_OVERLAP",
                        "Subscription periods do not overlap",
                        "error",
                        "temporal_integrity",
                        "subscriptions",
                        f"Subscription periods overlap for user {user_id}.",
                        field_name="period_start_timestamp",
                    )
                )
    return rules


def _assignment_rules(datasets: dict[str, list[Record]]) -> list[RuleResult]:
    rules: list[RuleResult] = []
    for record in datasets.get("experiment_assignments", []):
        exposure = _parse(str(record["exposure_timestamp"]))
        assignment = _parse(str(record["assignment_timestamp"]))
        conversion_value = record.get("conversion_timestamp")
        if exposure < assignment:
            rules.append(
                _cross_failure(
                    "experiment_assignments",
                    record,
                    "EXPOSURE_BEFORE_ASSIGNMENT",
                    "exposure_timestamp",
                )
            )
        if isinstance(conversion_value, str) and _parse(conversion_value) < exposure:
            rules.append(
                _cross_failure(
                    "experiment_assignments",
                    record,
                    "CONVERSION_BEFORE_EXPOSURE",
                    "conversion_timestamp",
                )
            )
        if bool(record["converted"]) != isinstance(conversion_value, str):
            rules.append(
                _cross_failure(
                    "experiment_assignments", record, "CONVERSION_FLAG_MISMATCH", "converted"
                )
            )
    return rules


def _feedback_rules(datasets: dict[str, list[Record]]) -> list[RuleResult]:
    signup_by_user = {
        str(row["user_id"]): _parse(str(row["signup_timestamp"]))
        for row in datasets.get("users", [])
    }
    rules: list[RuleResult] = []
    for record in datasets.get("customer_feedback", []):
        signup = signup_by_user.get(str(record["user_id"]))
        if signup and _parse(str(record["feedback_timestamp"])) < signup:
            rules.append(
                _cross_failure(
                    "customer_feedback", record, "FEEDBACK_BEFORE_SIGNUP", "feedback_timestamp"
                )
            )
    return rules


def _event_count_rules(datasets: dict[str, list[Record]]) -> list[RuleResult]:
    counts = Counter(str(row["session_id"]) for row in datasets.get("clickstream_events", []))
    rules: list[RuleResult] = []
    for session in datasets.get("sessions", []):
        if int(session["event_count"]) != counts[str(session["session_id"])]:
            rules.append(
                _cross_failure("sessions", session, "SESSION_EVENT_COUNT_MISMATCH", "event_count")
            )
    return rules


def _feature_usage_rules(datasets: dict[str, list[Record]]) -> list[RuleResult]:
    expected: dict[tuple[str, str, str], dict[str, int]] = defaultdict(
        lambda: {
            "usage_count": 0,
            "active_minutes": 0,
            "successful_action_count": 0,
            "error_count": 0,
        }
    )
    for event in datasets.get("clickstream_events", []):
        feature = event.get("feature_name")
        if feature is None:
            continue
        key = (str(event["user_id"]), str(feature), str(event["event_timestamp"])[:10])
        expected[key]["usage_count"] += 1
        expected[key]["active_minutes"] += 2
        event_type = EVENT_TAXONOMY[str(event["event_name"])].event_type
        if event_type == "success":
            expected[key]["successful_action_count"] += 1
        if event_type == "failure":
            expected[key]["error_count"] += 1
    actual = {
        (str(row["user_id"]), str(row["feature_name"]), str(row["observation_date"])): {
            "usage_count": int(row["usage_count"]),
            "active_minutes": int(row["active_minutes"]),
            "successful_action_count": int(row["successful_action_count"]),
            "error_count": int(row["error_count"]),
        }
        for row in datasets.get("feature_usage", [])
    }
    if dict(expected) == actual:
        return []
    return [
        failed_rule(
            "FEATURE_USAGE_RECONCILIATION_FAILED",
            "Feature usage reconciles to clickstream events",
            "error",
            "consistency",
            "feature_usage",
            "Feature usage aggregates do not reconcile to accepted clickstream events.",
            remediation="Regenerate feature usage or quarantine the inconsistent aggregate rows.",
        )
    ]


def _cross_failure(dataset: str, record: Record, rule_id: str, field_name: str) -> RuleResult:
    metadata = record.get("_ingestion_metadata")
    source_location = None
    if isinstance(metadata, dict):
        source_location = SourceLocation(
            str(metadata.get("source_file")),
            row_number=metadata.get("source_row_number")
            if isinstance(metadata.get("source_row_number"), int)
            else None,
            line_number=metadata.get("source_line_number")
            if isinstance(metadata.get("source_line_number"), int)
            else None,
        )
    return failed_rule(
        rule_id,
        rule_id.replace("_", " ").title(),
        "error",
        "referential_integrity" if rule_id.startswith("FK_") else "temporal_integrity",
        dataset,
        f"{rule_id} failed for field {field_name}.",
        source_location=source_location,
        field_name=field_name,
        offending_value=str(record.get(field_name)),
    )


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
