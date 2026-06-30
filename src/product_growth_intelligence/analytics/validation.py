"""Analytical output validation."""

from __future__ import annotations

from product_growth_intelligence.analytics.funnel_models import FunnelAttempt
from product_growth_intelligence.data_generation.models import Record


def validate_attempts(attempts: list[FunnelAttempt]) -> None:
    """Validate attempt invariants."""

    ids = [attempt.attempt_id for attempt in attempts]
    if len(ids) != len(set(ids)):
        msg = "Funnel attempt IDs must be unique."
        raise ValueError(msg)
    for attempt in attempts:
        timestamps = [attempt.stage_timestamps[stage] for stage in attempt.stages_reached]
        if timestamps != sorted(timestamps):
            msg = f"Stage timestamps are not monotonic for {attempt.attempt_id}."
            raise ValueError(msg)
        if attempt.attempt_status == "completed":
            if attempt.completion_timestamp is None:
                msg = f"Completed attempt {attempt.attempt_id} lacks completion timestamp."
                raise ValueError(msg)
            if attempt.completion_timestamp != timestamps[-1]:
                msg = f"Completion timestamp mismatch for {attempt.attempt_id}."
                raise ValueError(msg)


def validate_metric_rows(summary_rows: list[Record], stage_rows: list[Record]) -> None:
    """Validate core metric reconciliation and rates."""

    for row in summary_rows:
        eligible = int(row["eligible_users"])
        entrants = int(row["entrants"])
        completed = int(row["completed"])
        if entrants > eligible:
            msg = f"Entrants exceed eligible users for {row['funnel_id']}."
            raise ValueError(msg)
        if completed > entrants:
            msg = f"Completions exceed entrants for {row['funnel_id']}."
            raise ValueError(msg)
        _validate_rate(row.get("entry_rate"))
        _validate_rate(row.get("overall_conversion_rate"))
        _validate_rate(row.get("fully_observed_conversion_rate"))
    by_funnel: dict[str, list[Record]] = {}
    for row in stage_rows:
        by_funnel.setdefault(str(row["funnel_id"]), []).append(row)
        for field in (
            "eligible_reach_rate",
            "entrant_reach_rate",
            "step_conversion_rate",
            "cumulative_conversion_rate",
            "drop_off_rate",
        ):
            _validate_rate(row.get(field))
    for funnel_id, rows in by_funnel.items():
        ordered = sorted(rows, key=lambda row: int(row["stage_order"]))
        counts = [int(row["reached_count"]) for row in ordered]
        if counts != sorted(counts, reverse=True):
            msg = f"Stage counts are not monotonic for {funnel_id}."
            raise ValueError(msg)


def _validate_rate(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, int | float | str):
        msg = f"Rate is not numeric: {value}."
        raise ValueError(msg)
    numeric = float(value)
    if numeric < 0 or numeric > 1:
        msg = f"Rate is outside [0, 1]: {value}."
        raise ValueError(msg)
