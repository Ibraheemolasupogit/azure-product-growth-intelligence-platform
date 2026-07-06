"""Governed NexaFlow experiment catalogue and metric definitions."""

from __future__ import annotations

from product_growth_intelligence.experiments.models import ExperimentSpec, MetricSpec

EXPERIMENT_CATALOGUE_VERSION = "2026-07-milestone-9"
EXPERIMENT_METRIC_VERSION = "2026-07-milestone-9-metrics"


def experiment_metrics() -> dict[str, MetricSpec]:
    """Return governed experiment metric definitions keyed by metric ID."""

    metrics = (
        MetricSpec(
            "onboarding_completion_rate",
            "Onboarding completion rate",
            "binary",
            "Assigned users who complete onboarding inside the attribution window.",
            ("onboarding_completed",),
            practical_threshold=0.05,
        ),
        MetricSpec(
            "workspace_creation_rate",
            "Workspace creation rate",
            "binary",
            "Assigned users who create a workspace inside the attribution window.",
            ("workspace_created",),
            practical_threshold=0.04,
        ),
        MetricSpec(
            "activation_completion_rate",
            "Activation completion rate",
            "binary",
            "Assigned users who complete a task inside the attribution window.",
            ("task_completed",),
            practical_threshold=0.04,
        ),
        MetricSpec(
            "time_to_onboarding_hours",
            "Time to onboarding completion",
            "continuous",
            "Hours from attribution start to onboarding completion; capped at the window.",
            ("onboarding_completed",),
            direction="decrease",
            practical_threshold=12.0,
            unit="hours",
        ),
        MetricSpec(
            "collaboration_adoption_rate",
            "Collaboration adoption rate",
            "binary",
            "Assigned users with invite, share, member, or comment collaboration activity.",
            ("invite_sent", "project_shared", "member_added", "comment_added", "invite_accepted"),
            practical_threshold=0.05,
        ),
        MetricSpec(
            "template_selection_rate",
            "Template selection rate",
            "binary",
            "Assigned users who select a template inside the attribution window.",
            ("template_selected",),
            practical_threshold=0.04,
        ),
        MetricSpec(
            "recommendation_acceptance_rate",
            "Recommendation acceptance rate",
            "binary",
            "Assigned users who accept a recommendation inside the attribution window.",
            ("recommendation_accepted",),
            practical_threshold=0.04,
        ),
        MetricSpec(
            "paid_conversion_rate",
            "Paid conversion rate",
            "binary",
            "Assigned users who start a paid subscription inside the attribution window.",
            ("subscription_started",),
            practical_threshold=0.05,
        ),
        MetricSpec(
            "trial_start_rate",
            "Trial start rate",
            "binary",
            "Assigned users who start a trial inside the attribution window.",
            ("trial_started",),
            practical_threshold=0.05,
        ),
        MetricSpec(
            "upgrade_prompt_click_rate",
            "Upgrade prompt click rate",
            "binary",
            "Assigned users who click or accept an upgrade-style recommendation.",
            ("recommendation_clicked", "recommendation_accepted"),
            practical_threshold=0.04,
        ),
        MetricSpec(
            "automation_adoption_rate",
            "Automation adoption rate",
            "binary",
            "Assigned users who create an automation inside the attribution window.",
            ("automation_created",),
            practical_threshold=0.05,
        ),
        MetricSpec(
            "automation_execution_count",
            "Automation execution count",
            "count",
            "Automation execution events per assigned user inside the attribution window.",
            ("automation_executed",),
            practical_threshold=0.2,
            unit="events_per_user",
        ),
        MetricSpec(
            "session_depth",
            "Session depth",
            "continuous",
            "Mean events per active session inside the attribution window.",
            (),
            practical_threshold=0.5,
            unit="events_per_session",
        ),
        MetricSpec(
            "feature_error_rate",
            "Feature error rate",
            "binary",
            "Assigned users with a feature error inside the attribution window.",
            ("feature_error",),
            direction="decrease",
            guardrail=True,
            critical=True,
            harm_threshold=0.05,
        ),
        MetricSpec(
            "request_failure_rate",
            "Request failure rate",
            "binary",
            "Assigned users with request failures inside the attribution window.",
            ("request_failed",),
            direction="decrease",
            guardrail=True,
            critical=True,
            harm_threshold=0.05,
        ),
        MetricSpec(
            "reduced_task_completion_count",
            "Task completion count",
            "count",
            "Task completions per assigned user; decreases are treated as guardrail harm.",
            ("task_completed",),
            direction="increase",
            practical_threshold=0.2,
            guardrail=True,
            critical=False,
            harm_threshold=0.2,
            unit="events_per_user",
        ),
    )
    return {metric.metric_id: metric for metric in metrics}


def default_experiment_catalogue() -> tuple[ExperimentSpec, ...]:
    """Return the default governed experiment catalogue."""

    common_segments = (
        "persona",
        "acquisition_channel",
        "initial_plan",
        "company_size_band",
        "is_team_account",
        "region",
    )
    return (
        ExperimentSpec(
            experiment_id="exp_simplified_onboarding",
            experiment_name="Simplified onboarding",
            version=EXPERIMENT_CATALOGUE_VERSION,
            business_hypothesis="A simplified onboarding path improves setup completion.",
            randomisation_unit="user_id",
            eligibility_population="new_user",
            variants=("control", "simplified"),
            control_variant="control",
            treatment_variants=("simplified",),
            planned_allocation={"control": 0.5, "simplified": 0.5},
            assignment_start="2025-01-01T00:00:00Z",
            assignment_end="2025-03-31T23:59:59Z",
            exposure_event="onboarding_started",
            primary_metric="onboarding_completion_rate",
            secondary_metrics=(
                "workspace_creation_rate",
                "activation_completion_rate",
                "time_to_onboarding_hours",
                "session_depth",
            ),
            guardrail_metrics=("feature_error_rate", "request_failure_rate"),
            analysis_window_days=45,
            attribution_window_days=30,
            minimum_sample_size=50,
            minimum_detectable_effect=0.05,
            significance_level=0.05,
            target_power=0.8,
            segment_dimensions=common_segments,
            exclusion_rules=(
                "assignment_before_signup",
                "invalid_variant",
                "exposure_before_assignment",
            ),
            owner="Product activation",
        ),
        ExperimentSpec(
            experiment_id="exp_template_recommendation",
            experiment_name="Collaborative template recommendation",
            version=EXPERIMENT_CATALOGUE_VERSION,
            business_hypothesis="Recommended templates increase collaboration adoption.",
            randomisation_unit="user_id",
            eligibility_population="activated_user",
            variants=("control", "recommended_templates"),
            control_variant="control",
            treatment_variants=("recommended_templates",),
            planned_allocation={"control": 0.5, "recommended_templates": 0.5},
            assignment_start="2025-01-01T00:00:00Z",
            assignment_end="2025-03-31T23:59:59Z",
            exposure_event="recommendation_shown",
            primary_metric="collaboration_adoption_rate",
            secondary_metrics=(
                "template_selection_rate",
                "recommendation_acceptance_rate",
                "session_depth",
            ),
            guardrail_metrics=("feature_error_rate", "request_failure_rate"),
            analysis_window_days=45,
            attribution_window_days=30,
            minimum_sample_size=50,
            minimum_detectable_effect=0.05,
            significance_level=0.05,
            target_power=0.8,
            segment_dimensions=common_segments,
            exclusion_rules=(
                "assignment_before_signup",
                "invalid_variant",
                "exposure_before_assignment",
            ),
            owner="Collaboration product",
        ),
        ExperimentSpec(
            experiment_id="exp_trial_upgrade_prompt",
            experiment_name="Trial upgrade prompt",
            version=EXPERIMENT_CATALOGUE_VERSION,
            business_hypothesis="Contextual upgrade prompts improve paid conversion.",
            randomisation_unit="user_id",
            eligibility_population="free_or_trial_user",
            variants=("control", "contextual_prompt"),
            control_variant="control",
            treatment_variants=("contextual_prompt",),
            planned_allocation={"control": 0.5, "contextual_prompt": 0.5},
            assignment_start="2025-01-01T00:00:00Z",
            assignment_end="2025-03-31T23:59:59Z",
            exposure_event="upgrade_prompt_viewed",
            primary_metric="paid_conversion_rate",
            secondary_metrics=("trial_start_rate", "upgrade_prompt_click_rate", "session_depth"),
            guardrail_metrics=("feature_error_rate", "request_failure_rate"),
            analysis_window_days=45,
            attribution_window_days=30,
            minimum_sample_size=50,
            minimum_detectable_effect=0.05,
            significance_level=0.05,
            target_power=0.8,
            segment_dimensions=common_segments,
            exclusion_rules=(
                "assignment_before_signup",
                "invalid_variant",
                "exposure_before_assignment",
            ),
            owner="Monetisation",
        ),
        ExperimentSpec(
            experiment_id="exp_automation_discovery",
            experiment_name="Automation feature discovery",
            version=EXPERIMENT_CATALOGUE_VERSION,
            business_hypothesis="Guided discovery increases automation adoption.",
            randomisation_unit="user_id",
            eligibility_population="advanced_feature_user",
            variants=("control", "guided_discovery"),
            control_variant="control",
            treatment_variants=("guided_discovery",),
            planned_allocation={"control": 0.5, "guided_discovery": 0.5},
            assignment_start="2025-01-01T00:00:00Z",
            assignment_end="2025-03-31T23:59:59Z",
            exposure_event="recommendation_shown",
            primary_metric="automation_adoption_rate",
            secondary_metrics=("automation_execution_count", "session_depth"),
            guardrail_metrics=(
                "feature_error_rate",
                "request_failure_rate",
                "reduced_task_completion_count",
            ),
            analysis_window_days=45,
            attribution_window_days=30,
            minimum_sample_size=50,
            minimum_detectable_effect=0.05,
            significance_level=0.05,
            target_power=0.8,
            segment_dimensions=common_segments,
            exclusion_rules=(
                "assignment_before_signup",
                "invalid_variant",
                "exposure_before_assignment",
            ),
            owner="Automation product",
        ),
    )


def validate_experiment_catalogue(
    experiments: tuple[ExperimentSpec, ...],
    metrics: dict[str, MetricSpec],
) -> None:
    """Validate governed experiment specifications."""

    seen = set()
    for experiment in experiments:
        key = (experiment.experiment_id, experiment.version)
        if key in seen:
            msg = f"Duplicate experiment specification: {experiment.experiment_id}."
            raise ValueError(msg)
        seen.add(key)
        if experiment.control_variant not in experiment.variants:
            msg = f"Missing control variant for {experiment.experiment_id}."
            raise ValueError(msg)
        if not set(experiment.treatment_variants) <= set(experiment.variants):
            msg = f"Unknown treatment variant for {experiment.experiment_id}."
            raise ValueError(msg)
        if abs(sum(experiment.planned_allocation.values()) - 1.0) > 0.000001:
            msg = f"Invalid allocation proportions for {experiment.experiment_id}."
            raise ValueError(msg)
        if set(experiment.planned_allocation) != set(experiment.variants):
            msg = f"Allocation variants do not match variants for {experiment.experiment_id}."
            raise ValueError(msg)
        metric_ids = (
            experiment.primary_metric,
            *experiment.secondary_metrics,
            *experiment.guardrail_metrics,
        )
        missing = sorted(set(metric_ids) - set(metrics))
        if missing:
            msg = f"Unknown metrics for {experiment.experiment_id}: {missing}."
            raise ValueError(msg)
        if experiment.minimum_sample_size < 0:
            msg = f"Negative minimum sample size for {experiment.experiment_id}."
            raise ValueError(msg)
