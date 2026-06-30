"""Governed NexaFlow funnel definitions."""

from __future__ import annotations

from product_growth_intelligence.analytics.funnel_models import FunnelDefinition, FunnelStage
from product_growth_intelligence.data_generation.catalogues import EVENT_TAXONOMY

FUNNEL_VERSION = "2026-06-milestone-4"


def default_funnel_definitions() -> tuple[FunnelDefinition, ...]:
    """Return the default governed funnel definitions."""

    segments = (
        "persona",
        "acquisition_channel",
        "region",
        "device_preference",
        "initial_plan",
        "company_size_band",
        "is_team_account",
        "experiment_variant",
    )
    return (
        FunnelDefinition(
            funnel_id="account_activation",
            funnel_name="Account activation funnel",
            version=FUNNEL_VERSION,
            business_objective=(
                "How effectively do newly registered users reach meaningful first value?"
            ),
            analytical_entity="user",
            stages=(
                FunnelStage("account_created", "Account created", ("account_created",)),
                FunnelStage("onboarding_started", "Onboarding started", ("onboarding_started",)),
                FunnelStage(
                    "onboarding_completed", "Onboarding completed", ("onboarding_completed",)
                ),
                FunnelStage("workspace_created", "Workspace created", ("workspace_created",)),
                FunnelStage("project_created", "Project created", ("project_created",)),
                FunnelStage("task_created", "Task created", ("task_created",)),
                FunnelStage("task_completed", "Task completed", ("task_completed",)),
            ),
            allowed_completion_days=30,
            eligibility_rule="users_signed_up_within_analysis_window",
            conversion_outcome="task_completed",
            supported_segments=segments,
            product_owner="Growth analytics",
            metric_notes="First-entry user funnel using event time.",
        ),
        FunnelDefinition(
            funnel_id="onboarding",
            funnel_name="Onboarding funnel",
            version=FUNNEL_VERSION,
            business_objective="Where does onboarding friction cause users to abandon setup?",
            analytical_entity="user",
            stages=(
                FunnelStage("onboarding_started", "Onboarding started", ("onboarding_started",)),
                FunnelStage(
                    "onboarding_step_completed",
                    "Onboarding step completed",
                    ("onboarding_step_completed",),
                ),
                FunnelStage(
                    "onboarding_completed", "Onboarding completed", ("onboarding_completed",)
                ),
                FunnelStage("workspace_created", "Workspace created", ("workspace_created",)),
                FunnelStage(
                    "first_setup_action",
                    "Template or project selected",
                    ("template_selected", "project_created"),
                ),
            ),
            allowed_completion_days=14,
            eligibility_rule="users_with_onboarding_started",
            conversion_outcome="template_selected_or_project_created",
            supported_segments=segments,
            product_owner="Product activation",
            metric_notes="Alternative terminal setup action is allowed.",
        ),
        FunnelDefinition(
            funnel_id="collaboration_adoption",
            funnel_name="Collaboration adoption funnel",
            version=FUNNEL_VERSION,
            business_objective=(
                "How successfully do team-oriented users adopt collaborative workflows?"
            ),
            analytical_entity="user",
            stages=(
                FunnelStage("workspace_created", "Workspace created", ("workspace_created",)),
                FunnelStage("project_created", "Project created", ("project_created",)),
                FunnelStage("invite_sent", "Invite sent", ("invite_sent",)),
                FunnelStage(
                    "teammate_joined",
                    "Invite accepted or member added",
                    ("invite_accepted", "member_added"),
                ),
                FunnelStage(
                    "collaboration_signal",
                    "Project shared or comment added",
                    ("project_shared", "comment_added"),
                ),
            ),
            allowed_completion_days=30,
            eligibility_rule="team_accounts_or_team_oriented_personas",
            conversion_outcome="project_shared_or_comment_added",
            supported_segments=segments,
            product_owner="Collaboration product",
            metric_notes="Descriptive collaboration workflow adoption.",
        ),
        FunnelDefinition(
            funnel_id="trial_to_paid",
            funnel_name="Trial-to-paid funnel",
            version=FUNNEL_VERSION,
            business_objective="How efficiently do monetisation prompts lead to paid conversion?",
            analytical_entity="user",
            stages=(
                FunnelStage(
                    "upgrade_prompt_viewed", "Upgrade prompt viewed", ("upgrade_prompt_viewed",)
                ),
                FunnelStage("trial_started", "Trial started", ("trial_started",)),
                FunnelStage(
                    "subscription_started", "Subscription started", ("subscription_started",)
                ),
                FunnelStage(
                    "paid_conversion",
                    "Paid conversion",
                    ("plan_upgraded",),
                    subscription_paid_outcome=True,
                ),
            ),
            allowed_completion_days=45,
            eligibility_rule="users_exposed_to_upgrade_prompt_or_trial_eligible",
            conversion_outcome="plan_upgraded_or_paid_subscription",
            supported_segments=segments,
            product_owner="Monetisation",
            metric_notes="Paid outcome may be confirmed from subscription records.",
        ),
        FunnelDefinition(
            funnel_id="automation_adoption",
            funnel_name="Automation adoption funnel",
            version=FUNNEL_VERSION,
            business_objective=(
                "Do users discover, successfully execute and repeatedly adopt automation?"
            ),
            analytical_entity="user",
            stages=(
                FunnelStage("automation_created", "Automation created", ("automation_created",)),
                FunnelStage("automation_executed", "Automation executed", ("automation_executed",)),
                FunnelStage(
                    "repeated_automation_use",
                    "Repeated automation use",
                    ("automation_executed",),
                    minimum_event_count=2,
                ),
            ),
            allowed_completion_days=30,
            eligibility_rule="users_with_automation_access_or_creation",
            conversion_outcome="two_automation_executions",
            supported_segments=segments,
            product_owner="Automation product",
            metric_notes="Repeated use requires two automation_executed events.",
        ),
        FunnelDefinition(
            funnel_id="recommendation_interaction",
            funnel_name="Recommendation interaction funnel",
            version=FUNNEL_VERSION,
            business_objective=(
                "How often do product recommendations progress from exposure to acceptance?"
            ),
            analytical_entity="user",
            stages=(
                FunnelStage(
                    "recommendation_shown", "Recommendation shown", ("recommendation_shown",)
                ),
                FunnelStage(
                    "recommendation_clicked", "Recommendation clicked", ("recommendation_clicked",)
                ),
                FunnelStage(
                    "recommendation_accepted",
                    "Recommendation accepted",
                    ("recommendation_accepted",),
                ),
            ),
            allowed_completion_days=45,
            eligibility_rule="users_with_recommendation_exposure",
            conversion_outcome="recommendation_accepted",
            supported_segments=segments,
            product_owner="Recommendations product",
            metric_notes="Interaction analytics only; no recommendation model is implemented.",
        ),
    )


def validate_funnel_definitions(definitions: tuple[FunnelDefinition, ...]) -> None:
    """Validate governed funnel definitions before analysis."""

    seen = set()
    for definition in definitions:
        key = (definition.funnel_id, definition.version)
        if key in seen:
            msg = f"Duplicate funnel definition: {definition.funnel_id} {definition.version}."
            raise ValueError(msg)
        seen.add(key)
        if len(definition.stages) < 2:
            msg = f"Funnel {definition.funnel_id} must have at least two stages."
            raise ValueError(msg)
        if definition.allowed_completion_days <= 0:
            msg = f"Funnel {definition.funnel_id} has non-positive completion window."
            raise ValueError(msg)
        for stage in definition.stages:
            if stage.minimum_event_count < 1:
                msg = f"Stage {stage.stage_id} has invalid minimum event count."
                raise ValueError(msg)
            unknown = set(stage.event_names) - set(EVENT_TAXONOMY)
            if unknown:
                msg = f"Stage {stage.stage_id} references unknown events: {sorted(unknown)}."
                raise ValueError(msg)


def definitions_by_id(
    definitions: tuple[FunnelDefinition, ...] | None = None,
) -> dict[str, FunnelDefinition]:
    """Return funnel definitions keyed by ID."""

    items = definitions or default_funnel_definitions()
    return {definition.funnel_id: definition for definition in items}
