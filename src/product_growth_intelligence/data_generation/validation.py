"""Cross-dataset validation for generated NexaFlow data."""

from collections import Counter, defaultdict
from datetime import datetime

from product_growth_intelligence.data_generation.catalogues import (
    EVENT_TAXONOMY,
    EXPERIMENT_CATALOGUE,
    FEEDBACK_TEMPLATES,
    PLAN_CATALOGUE,
)
from product_growth_intelligence.data_generation.models import GeneratedDatasets, Record


class SyntheticDataValidationError(ValueError):
    """Raised when generated data violates a documented contract."""


def validate_datasets(datasets: GeneratedDatasets) -> None:
    """Validate generated datasets and raise on the first detected failure."""

    _validate_unique(datasets.users, "user_id", "users")
    _validate_unique(datasets.sessions, "session_id", "sessions")
    _validate_unique(datasets.clickstream_events, "event_id", "clickstream_events")
    _validate_unique(datasets.feature_usage, "usage_id", "feature_usage")
    _validate_unique(datasets.subscriptions, "subscription_id", "subscriptions")
    _validate_unique(datasets.experiment_assignments, "assignment_id", "experiment_assignments")
    _validate_unique(datasets.customer_feedback, "feedback_id", "customer_feedback")

    user_ids = {str(record["user_id"]) for record in datasets.users}
    session_ids = {str(record["session_id"]) for record in datasets.sessions}
    _validate_references(datasets.sessions, "user_id", user_ids, "sessions.user_id")
    _validate_references(datasets.clickstream_events, "user_id", user_ids, "events.user_id")
    _validate_references(
        datasets.clickstream_events, "session_id", session_ids, "events.session_id"
    )
    _validate_references(datasets.feature_usage, "user_id", user_ids, "feature_usage.user_id")
    _validate_references(datasets.subscriptions, "user_id", user_ids, "subscriptions.user_id")
    _validate_references(
        datasets.experiment_assignments, "user_id", user_ids, "assignments.user_id"
    )
    _validate_references(datasets.customer_feedback, "user_id", user_ids, "feedback.user_id")

    _validate_temporal_integrity(datasets)
    _validate_domain_integrity(datasets)
    _validate_aggregate_consistency(datasets)


def _validate_unique(records: list[Record], key: str, dataset_name: str) -> None:
    values = [record[key] for record in records]
    duplicates = [value for value, count in Counter(values).items() if count > 1]
    if duplicates:
        msg = f"{dataset_name} contains duplicate {key}: {duplicates[0]}"
        raise SyntheticDataValidationError(msg)


def _validate_references(
    records: list[Record], key: str, allowed_values: set[str], field_name: str
) -> None:
    for record in records:
        if str(record[key]) not in allowed_values:
            msg = f"{field_name} references unknown value {record[key]}."
            raise SyntheticDataValidationError(msg)


def _validate_temporal_integrity(datasets: GeneratedDatasets) -> None:
    signup_by_user = {
        str(user["user_id"]): _parse(str(user["signup_timestamp"])) for user in datasets.users
    }
    sessions_by_id = {str(session["session_id"]): session for session in datasets.sessions}

    first_session_by_user: dict[str, datetime] = {}
    for session in datasets.sessions:
        user_id = str(session["user_id"])
        start = _parse(str(session["session_start_timestamp"]))
        end = _parse(str(session["session_end_timestamp"]))
        if end < start:
            msg = f"Session {session['session_id']} ends before it starts."
            raise SyntheticDataValidationError(msg)
        first_session_by_user[user_id] = min(first_session_by_user.get(user_id, start), start)

    for user_id, first_session in first_session_by_user.items():
        if signup_by_user[user_id] > first_session:
            msg = f"User {user_id} signs up after first session."
            raise SyntheticDataValidationError(msg)

    sequences_by_session: dict[str, list[int]] = defaultdict(list)
    for event in datasets.clickstream_events:
        session = sessions_by_id[str(event["session_id"])]
        event_time = _parse(str(event["event_timestamp"]))
        if (
            not _parse(str(session["session_start_timestamp"]))
            <= event_time
            <= _parse(str(session["session_end_timestamp"]))
        ):
            msg = f"Event {event['event_id']} falls outside its session."
            raise SyntheticDataValidationError(msg)
        sequences_by_session[str(event["session_id"])].append(int(event["event_sequence_number"]))

    for session_id, sequences in sequences_by_session.items():
        if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            msg = f"Event sequence numbers are invalid for session {session_id}."
            raise SyntheticDataValidationError(msg)

    periods_by_user: dict[str, list[tuple[datetime, datetime | None]]] = defaultdict(list)
    for subscription in datasets.subscriptions:
        start = _parse(str(subscription["period_start_timestamp"]))
        end_value = subscription["period_end_timestamp"]
        subscription_end = _parse(str(end_value)) if isinstance(end_value, str) else None
        if subscription_end is not None and subscription_end < start:
            msg = f"Subscription {subscription['subscription_id']} ends before it starts."
            raise SyntheticDataValidationError(msg)
        periods_by_user[str(subscription["user_id"])].append((start, subscription_end))

    for user_id, periods in periods_by_user.items():
        ordered = sorted(periods, key=lambda item: item[0])
        for current, next_period in zip(ordered, ordered[1:], strict=False):
            current_end = current[1]
            if current_end is None or current_end > next_period[0]:
                msg = f"Subscription periods overlap for user {user_id}."
                raise SyntheticDataValidationError(msg)

    for assignment in datasets.experiment_assignments:
        exposure = _parse(str(assignment["exposure_timestamp"]))
        assigned = _parse(str(assignment["assignment_timestamp"]))
        if exposure < assigned:
            msg = f"Experiment exposure precedes assignment for {assignment['assignment_id']}."
            raise SyntheticDataValidationError(msg)
        conversion_value = assignment["conversion_timestamp"]
        if isinstance(conversion_value, str) and _parse(conversion_value) < exposure:
            msg = f"Experiment conversion precedes exposure for {assignment['assignment_id']}."
            raise SyntheticDataValidationError(msg)

    for feedback in datasets.customer_feedback:
        if _parse(str(feedback["feedback_timestamp"])) < signup_by_user[str(feedback["user_id"])]:
            msg = f"Feedback precedes signup for {feedback['feedback_id']}."
            raise SyntheticDataValidationError(msg)


def _validate_domain_integrity(datasets: GeneratedDatasets) -> None:
    for event in datasets.clickstream_events:
        event_name = str(event["event_name"])
        if event_name not in EVENT_TAXONOMY:
            msg = f"Unknown event name {event_name}."
            raise SyntheticDataValidationError(msg)
        expected_feature = EVENT_TAXONOMY[event_name].feature_name
        if event["feature_name"] != expected_feature:
            msg = f"Event {event_name} has incompatible feature {event['feature_name']}."
            raise SyntheticDataValidationError(msg)

    for subscription in datasets.subscriptions:
        if str(subscription["plan_name"]) not in PLAN_CATALOGUE:
            msg = f"Unknown plan {subscription['plan_name']}."
            raise SyntheticDataValidationError(msg)
        if float(subscription["monthly_recurring_revenue"]) < 0:
            msg = "Monthly recurring revenue cannot be negative."
            raise SyntheticDataValidationError(msg)

    for assignment in datasets.experiment_assignments:
        experiment_id = str(assignment["experiment_id"])
        if experiment_id not in EXPERIMENT_CATALOGUE:
            msg = f"Unknown experiment {experiment_id}."
            raise SyntheticDataValidationError(msg)
        if str(assignment["variant"]) not in EXPERIMENT_CATALOGUE[experiment_id]["variants"]:
            msg = f"Invalid variant {assignment['variant']} for {experiment_id}."
            raise SyntheticDataValidationError(msg)
        if bool(assignment["converted"]) != isinstance(assignment["conversion_timestamp"], str):
            msg = f"Conversion flag/timestamp mismatch for {assignment['assignment_id']}."
            raise SyntheticDataValidationError(msg)

    template_texts = {text for templates in FEEDBACK_TEMPLATES.values() for text in templates}
    for feedback in datasets.customer_feedback:
        if int(feedback["rating"]) not in {1, 2, 3, 4, 5}:
            msg = f"Feedback rating is outside the valid range for {feedback['feedback_id']}."
            raise SyntheticDataValidationError(msg)
        if str(feedback["feedback_text"]) not in template_texts:
            msg = "Feedback text is not from the controlled template catalogue."
            raise SyntheticDataValidationError(msg)

    for usage in datasets.feature_usage:
        if any(
            int(usage[field]) < 0
            for field in ("usage_count", "active_minutes", "successful_action_count", "error_count")
        ):
            msg = f"Feature usage contains negative counts for {usage['usage_id']}."
            raise SyntheticDataValidationError(msg)


def _validate_aggregate_consistency(datasets: GeneratedDatasets) -> None:
    event_counts = Counter(str(event["session_id"]) for event in datasets.clickstream_events)
    for session in datasets.sessions:
        if int(session["event_count"]) != event_counts[str(session["session_id"])]:
            msg = f"Session event count mismatch for {session['session_id']}."
            raise SyntheticDataValidationError(msg)

    expected_usage: dict[tuple[str, str, str], dict[str, int]] = defaultdict(
        lambda: {
            "usage_count": 0,
            "active_minutes": 0,
            "successful_action_count": 0,
            "error_count": 0,
        }
    )
    for event in datasets.clickstream_events:
        feature = event["feature_name"]
        if feature is None:
            continue
        key = (str(event["user_id"]), str(feature), str(event["event_timestamp"])[:10])
        expected_usage[key]["usage_count"] += 1
        expected_usage[key]["active_minutes"] += 2
        event_type = EVENT_TAXONOMY[str(event["event_name"])].event_type
        if event_type == "success":
            expected_usage[key]["successful_action_count"] += 1
        if event_type == "failure":
            expected_usage[key]["error_count"] += 1

    actual_usage = {
        (str(row["user_id"]), str(row["feature_name"]), str(row["observation_date"])): {
            "usage_count": int(row["usage_count"]),
            "active_minutes": int(row["active_minutes"]),
            "successful_action_count": int(row["successful_action_count"]),
            "error_count": int(row["error_count"]),
        }
        for row in datasets.feature_usage
    }
    if dict(expected_usage) != actual_usage:
        msg = "Feature usage does not reconcile to clickstream events."
        raise SyntheticDataValidationError(msg)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
