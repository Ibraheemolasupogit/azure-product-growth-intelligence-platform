"""Governed retention definitions."""

from __future__ import annotations

from product_growth_intelligence.analytics.retention.models import (
    DEFAULT_RETENTION_SEGMENTS,
    ActivityRule,
    RetentionDefinition,
    TimeGrain,
)
from product_growth_intelligence.data_generation.catalogues import EVENT_TAXONOMY

RETENTION_VERSION = "2026-07-milestone-5"

DEFAULT_QUALIFYING_EVENTS = tuple(
    event_name
    for event_name, spec in EVENT_TAXONOMY.items()
    if event_name
    not in {
        "session_started",
        "feature_error",
        "request_failed",
        "recommendation_shown",
    }
    and spec.event_type != "failure"
)


def default_retention_definitions(
    time_grain: TimeGrain = "weekly", horizon: int = 8
) -> tuple[RetentionDefinition, ...]:
    """Return default retention definitions."""

    def build(
        definition_id: str,
        name: str,
        business_objective: str,
        anchor_rule: str,
        eligibility_rule: str,
    ) -> RetentionDefinition:
        return RetentionDefinition(
            definition_id=definition_id,
            name=name,
            version=RETENTION_VERSION,
            business_objective=business_objective,
            anchor_rule=anchor_rule,
            eligibility_rule=eligibility_rule,
            activity_rule=ActivityRule(DEFAULT_QUALIFYING_EVENTS),
            time_grain=time_grain,
            maximum_horizon=horizon,
            inactivity_threshold_periods=2,
            churn_threshold_periods=4,
            resurrection_rule="active_after_one_or_more_inactive_periods",
            supported_segments=DEFAULT_RETENTION_SEGMENTS,
            metric_notes="Classic and rolling retention use observed denominators only.",
            owner="Growth analytics",
        )

    return (
        build(
            "signup_retention",
            "Signup retention",
            business_objective="Do newly registered users continue using NexaFlow after signup?",
            anchor_rule="signup_timestamp",
            eligibility_rule="all_users_signed_up_in_window",
        ),
        build(
            "activation_retention",
            "Activation retention",
            business_objective="Do activated users return and remain engaged?",
            anchor_rule="first_task_completed_or_workspace_created",
            eligibility_rule="users_with_activation_event",
        ),
        build(
            "paid_user_retention",
            "Paid-user retention",
            business_objective="Do converted users remain active after becoming paying customers?",
            anchor_rule="first_paid_subscription_start",
            eligibility_rule="users_with_paid_subscription",
        ),
        build(
            "collaboration_user_retention",
            "Collaboration-user retention",
            business_objective="Are collaboration adopters more likely to remain active?",
            anchor_rule="first_collaboration_action",
            eligibility_rule="users_with_collaboration_action",
        ),
        build(
            "automation_user_retention",
            "Automation-user retention",
            business_objective="Do automation adopters continue returning to the product?",
            anchor_rule="first_automation_executed",
            eligibility_rule="users_with_automation_executed",
        ),
        build(
            "recommendation_engaged_retention",
            "Recommendation-engaged retention",
            business_objective="How does return behaviour differ for recommendation-engaged users?",
            anchor_rule="first_recommendation_click_or_accept",
            eligibility_rule="users_with_recommendation_click_or_accept",
        ),
    )


def validate_retention_definitions(definitions: tuple[RetentionDefinition, ...]) -> None:
    """Validate definition IDs, thresholds, horizons and event references."""

    seen = set()
    for definition in definitions:
        key = (definition.definition_id, definition.version)
        if key in seen:
            msg = f"Duplicate retention definition: {definition.definition_id}."
            raise ValueError(msg)
        seen.add(key)
        if definition.time_grain not in {"daily", "weekly", "monthly"}:
            msg = f"Unsupported grain for {definition.definition_id}."
            raise ValueError(msg)
        if definition.maximum_horizon < 0:
            msg = f"Negative horizon for {definition.definition_id}."
            raise ValueError(msg)
        if definition.activity_rule.minimum_event_count <= 0:
            msg = f"Invalid activity threshold for {definition.definition_id}."
            raise ValueError(msg)
        if definition.churn_threshold_periods < definition.inactivity_threshold_periods:
            msg = f"Invalid churn threshold for {definition.definition_id}."
            raise ValueError(msg)
        unknown = set(definition.activity_rule.event_names) - set(EVENT_TAXONOMY)
        if unknown:
            msg = f"Unknown activity events for {definition.definition_id}: {sorted(unknown)}."
            raise ValueError(msg)


def definitions_by_id(
    definitions: tuple[RetentionDefinition, ...] | None = None,
) -> dict[str, RetentionDefinition]:
    """Return definitions keyed by ID."""

    items = definitions or default_retention_definitions()
    return {definition.definition_id: definition for definition in items}
