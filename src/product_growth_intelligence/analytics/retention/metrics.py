"""Retention, lifecycle and segment metrics."""

from __future__ import annotations

from collections import defaultdict
from statistics import median

from product_growth_intelligence.analytics.retention.models import (
    CohortMembership,
    RetentionDefinition,
    UserPeriodActivity,
)
from product_growth_intelligence.analytics.retention.periods import parse_timestamp
from product_growth_intelligence.data_generation.models import Record


def retention_long_rows(
    definitions: tuple[RetentionDefinition, ...],
    memberships: list[CohortMembership],
    periods: list[UserPeriodActivity],
    suppression_threshold: int,
) -> list[Record]:
    """Calculate canonical long-format classic and rolling retention."""

    members_by_key = _members_by_definition_period(memberships)
    periods_by_key = _periods_by_definition_period(periods)
    rows: list[Record] = []
    for definition in definitions:
        cohort_periods = sorted(
            {
                membership.cohort_period
                for membership in memberships
                if membership.definition_id == definition.definition_id
            }
        )
        for cohort_period in cohort_periods:
            cohort_members = members_by_key[(definition.definition_id, cohort_period)]
            cohort_size = len(cohort_members)
            for index in range(definition.maximum_horizon + 1):
                period_rows = [
                    row for row in periods_by_key[(definition.definition_id, cohort_period, index)]
                ]
                observed = [row for row in period_rows if row.observed]
                retained_users = sum(1 for row in observed if row.active)
                rolling_users = _rolling_users(
                    periods, definition.definition_id, cohort_period, index
                )
                observed_denominator = len(observed)
                censored = cohort_size - observed_denominator
                suppressed = observed_denominator < suppression_threshold
                rows.append(
                    {
                        "definition_id": definition.definition_id,
                        "definition_version": definition.version,
                        "cohort_period": cohort_period,
                        "period_index": index,
                        "cohort_size": cohort_size,
                        "observed_denominator": observed_denominator,
                        "censored_users": censored,
                        "retained_users": retained_users,
                        "classic_retention_rate": None
                        if suppressed
                        else _rate(retained_users, observed_denominator),
                        "rolling_retained_users": rolling_users,
                        "rolling_retention_rate": None
                        if suppressed
                        else _rate(rolling_users, observed_denominator),
                        "active_users": retained_users,
                        "active_user_rate": None
                        if suppressed
                        else _rate(retained_users, observed_denominator),
                        "suppression_status": "suppressed" if suppressed else "shown",
                    }
                )
    return rows


def retention_matrix_rows(long_rows: list[Record]) -> list[Record]:
    """Create wide matrix rows from long-format retention rows."""

    grouped: dict[tuple[str, str, str], list[Record]] = defaultdict(list)
    for row in long_rows:
        grouped[
            (str(row["definition_id"]), str(row["definition_version"]), str(row["cohort_period"]))
        ].append(row)
    rows: list[Record] = []
    for (definition_id, version, cohort_period), items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda row: int(row["period_index"]))
        output: Record = {
            "definition_id": definition_id,
            "definition_version": version,
            "cohort_grain": "user",
            "cohort_period": cohort_period,
            "cohort_size": ordered[0]["cohort_size"] if ordered else 0,
        }
        for row in ordered:
            output[f"period_{row['period_index']}"] = row["classic_retention_rate"]
        rows.append(output)
    return rows


def cohort_summary_rows(
    definitions: tuple[RetentionDefinition, ...],
    memberships: list[CohortMembership],
    periods: list[UserPeriodActivity],
) -> list[Record]:
    """Calculate one summary row per definition and cohort period."""

    rows: list[Record] = []
    members_by_key = _members_by_definition_period(memberships)
    periods_by_membership: dict[str, list[UserPeriodActivity]] = defaultdict(list)
    for row in periods:
        periods_by_membership[row.membership_id].append(row)
    for definition in definitions:
        cohort_periods = sorted(
            {
                membership.cohort_period
                for membership in memberships
                if membership.definition_id == definition.definition_id
            }
        )
        for cohort_period in cohort_periods:
            members = members_by_key[(definition.definition_id, cohort_period)]
            returned = 0
            active_period_counts = []
            days_to_first_return = []
            inactive_users = 0
            resurrected_users = 0
            censored_users = 0
            for member in members:
                rows_for_member = sorted(
                    periods_by_membership[member.membership_id], key=lambda row: row.period_index
                )
                active_indexes = [row.period_index for row in rows_for_member if row.active]
                active_period_counts.append(len(active_indexes))
                if any(index > 0 for index in active_indexes):
                    returned += 1
                    first_return = next(index for index in active_indexes if index > 0)
                    anchor = parse_timestamp(member.anchor_timestamp)
                    period_row = rows_for_member[first_return]
                    days_to_first_return.append(
                        (parse_timestamp(period_row.period_start) - anchor).days
                    )
                inactive_users += int(not active_indexes)
                resurrected_users += int(_has_resurrection(rows_for_member))
                censored_users += int(any(not row.observed for row in rows_for_member))
            rows.append(
                {
                    "definition_id": definition.definition_id,
                    "cohort_period": cohort_period,
                    "cohort_size": len(members),
                    "users_returning_after_period_0": returned,
                    "return_rate": _rate(returned, len(members)),
                    "median_active_periods": _median_int(active_period_counts),
                    "median_days_to_first_return": _median_int(days_to_first_return),
                    "inactive_users": inactive_users,
                    "resurrected_users": resurrected_users,
                    "censored_users": censored_users,
                    "status": "passed",
                }
            )
    return rows


def segment_retention_rows(
    memberships: list[CohortMembership],
    periods: list[UserPeriodActivity],
    segment_dimensions: tuple[str, ...],
    suppression_threshold: int,
) -> tuple[list[Record], list[Record]]:
    """Calculate descriptive segment retention."""

    membership_by_id = {membership.membership_id: membership for membership in memberships}
    rows: list[Record] = []
    suppressed: list[Record] = []
    grouped: dict[tuple[str, str, int, str, str], list[UserPeriodActivity]] = defaultdict(list)
    for period in periods:
        membership = membership_by_id[period.membership_id]
        for dimension in segment_dimensions:
            value = str(membership.segments.get(dimension))
            grouped[
                (
                    membership.definition_id,
                    dimension,
                    period.period_index,
                    value,
                    membership.cohort_period,
                )
            ].append(period)
    for (definition_id, dimension, period_index, value, cohort_period), group in sorted(
        grouped.items()
    ):
        observed = [row for row in group if row.observed]
        retained = sum(1 for row in observed if row.active)
        if len(observed) < suppression_threshold:
            status = "suppressed"
            suppressed.append(
                {
                    "definition_id": definition_id,
                    "segment_dimension": dimension,
                    "segment_value": value,
                    "period_index": period_index,
                    "observed_denominator": len(observed),
                }
            )
        else:
            status = "shown"
        rows.append(
            {
                "definition_id": definition_id,
                "cohort_period": cohort_period,
                "segment_dimension": dimension,
                "segment_value": value,
                "period_index": period_index,
                "observed_denominator": len(observed),
                "retained_users": retained,
                "retention_rate": None
                if status == "suppressed"
                else _rate(retained, len(observed)),
                "suppression_status": status,
            }
        )
    return rows, suppressed


def lifecycle_rows(
    memberships: list[CohortMembership],
    periods: list[UserPeriodActivity],
    inactivity_threshold: int,
    churn_threshold: int,
) -> list[Record]:
    """Classify lifecycle status by user period."""

    membership_by_id = {membership.membership_id: membership for membership in memberships}
    grouped: dict[str, list[UserPeriodActivity]] = defaultdict(list)
    for period in periods:
        grouped[period.membership_id].append(period)
    rows: list[Record] = []
    for membership_id, items in sorted(grouped.items()):
        inactive_streak = 0
        prior = None
        for row in sorted(items, key=lambda item: item.period_index):
            if not row.observed:
                status = "censored"
            elif row.period_index == 0:
                status = "new" if row.active else "inactive"
            elif row.active and inactive_streak >= inactivity_threshold:
                status = "resurrected"
            elif row.active:
                status = "active"
            elif inactive_streak + 1 >= churn_threshold:
                status = "churned_descriptive"
            else:
                status = "inactive"
            rows.append(
                {
                    "user_id": row.user_id,
                    "definition_id": row.definition_id,
                    "period": row.period_start,
                    "activity_status": "active" if row.active else "inactive",
                    "prior_activity_status": prior,
                    "active_flag": row.active,
                    "inactivity_duration": inactive_streak if row.active else inactive_streak + 1,
                    "subscription_status": "separate_not_modelled",
                    "lifecycle_classification": status,
                    "resurrection_flag": status == "resurrected",
                    "source_ingestion_run_id": membership_by_id[
                        membership_id
                    ].source_ingestion_run_id,
                }
            )
            if row.observed:
                inactive_streak = 0 if row.active else inactive_streak + 1
                prior = "active" if row.active else "inactive"
    return rows


def resurrection_rows(lifecycle: list[Record]) -> list[Record]:
    """Summarise resurrection by definition."""

    grouped: dict[str, list[Record]] = defaultdict(list)
    for row in lifecycle:
        grouped[str(row["definition_id"])].append(row)
    rows: list[Record] = []
    for definition_id, items in sorted(grouped.items()):
        inactive = sum(
            1
            for row in items
            if row["lifecycle_classification"] in {"inactive", "churned_descriptive"}
        )
        resurrected = sum(1 for row in items if row["resurrection_flag"])
        rows.append(
            {
                "cohort_or_segment": definition_id,
                "inactive_users": inactive,
                "resurrected_users": resurrected,
                "resurrection_rate": _rate(resurrected, inactive),
                "median_inactive_duration_before_return": None,
                "first_return_feature_or_event_family": None,
            }
        )
    return rows


def _members_by_definition_period(
    memberships: list[CohortMembership],
) -> dict[tuple[str, str], list[CohortMembership]]:
    grouped: dict[tuple[str, str], list[CohortMembership]] = defaultdict(list)
    for membership in memberships:
        grouped[(membership.definition_id, membership.cohort_period)].append(membership)
    return grouped


def _periods_by_definition_period(
    periods: list[UserPeriodActivity],
) -> dict[tuple[str, str, int], list[UserPeriodActivity]]:
    grouped: dict[tuple[str, str, int], list[UserPeriodActivity]] = defaultdict(list)
    for period in periods:
        grouped[(period.definition_id, period.cohort_period, period.period_index)].append(period)
    return grouped


def _rolling_users(
    periods: list[UserPeriodActivity], definition_id: str, cohort_period: str, index: int
) -> int:
    users = {
        row.user_id
        for row in periods
        if row.definition_id == definition_id
        and row.cohort_period == cohort_period
        and row.period_index >= index
        and row.observed
        and row.active
    }
    return len(users)


def _has_resurrection(rows: list[UserPeriodActivity]) -> bool:
    inactive_seen = False
    for row in sorted(rows, key=lambda item: item.period_index):
        if not row.observed:
            continue
        if row.active and inactive_seen:
            return True
        if not row.active:
            inactive_seen = True
    return False


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def _median_int(values: list[int]) -> int | None:
    if not values:
        return None
    return int(median(values))
