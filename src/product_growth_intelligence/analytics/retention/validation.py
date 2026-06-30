"""Analytical validation for retention outputs."""

from __future__ import annotations

from product_growth_intelligence.analytics.retention.models import (
    CohortMembership,
    UserPeriodActivity,
)
from product_growth_intelligence.data_generation.models import Record


def validate_retention_outputs(
    memberships: list[CohortMembership],
    periods: list[UserPeriodActivity],
    long_rows: list[Record],
) -> None:
    """Validate core retention reconciliation."""

    membership_keys = [(row.definition_id, row.user_id) for row in memberships]
    if len(membership_keys) != len(set(membership_keys)):
        msg = "Expected one retention membership per user and definition."
        raise ValueError(msg)
    period_keys = [(row.membership_id, row.definition_id, row.period_index) for row in periods]
    if len(period_keys) != len(set(period_keys)):
        msg = "User-period activity keys must be unique."
        raise ValueError(msg)
    for row in long_rows:
        cohort_size = int(row["cohort_size"])
        observed = int(row["observed_denominator"])
        censored = int(row["censored_users"])
        retained = int(row["retained_users"])
        rolling = int(row["rolling_retained_users"])
        if observed > cohort_size or retained > observed:
            msg = f"Retention denominator reconciliation failed for {row['definition_id']}."
            raise ValueError(msg)
        if observed + censored != cohort_size:
            msg = f"Censoring reconciliation failed for {row['definition_id']}."
            raise ValueError(msg)
        if rolling < retained:
            msg = f"Rolling retention is below classic retention for {row['definition_id']}."
            raise ValueError(msg)
        for field in ("classic_retention_rate", "rolling_retention_rate", "active_user_rate"):
            value = row[field]
            if value is not None and not 0 <= float(value) <= 1:
                msg = f"Rate outside [0, 1]: {value}."
                raise ValueError(msg)
