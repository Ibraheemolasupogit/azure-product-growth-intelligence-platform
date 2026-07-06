# Experiment Analysis Report

All data is synthetic. This is fixed-window offline experiment analysis, not
online experimentation infrastructure or an automatic rollout decision.

## Simplified onboarding

Hypothesis: A simplified onboarding path improves setup completion.
Variants: control, simplified.
SRM status: pass (p=0.563703).
Primary metric onboarding_completion_rate: effect 0.5 with CI [-0.192952, 1.192952], adjusted p=0.676333.
Guardrails: failed feature_error_rate.
Decision: do_not_ship (critical_guardrail_harm).

## Collaborative template recommendation

Hypothesis: Recommended templates increase collaboration adoption.
Variants: control, recommended_templates.
SRM status: pass (p=0.563703).
Primary metric collaboration_adoption_rate: effect 0.0 with CI [0.0, 0.0], adjusted p=1.0.
Guardrails: failed request_failure_rate.
Decision: do_not_ship (critical_guardrail_harm).

## Trial upgrade prompt

Hypothesis: Contextual upgrade prompts improve paid conversion.
Variants: control, contextual_prompt.
SRM status: pass (p=0.563703).
Primary metric paid_conversion_rate: effect 0.0 with CI [0.0, 0.0], adjusted p=1.0.
Guardrails: passed.
Decision: no_clear_evidence (primary_metric_not_statistically_or_practically_clear).

## Automation feature discovery

Hypothesis: Guided discovery increases automation adoption.
Variants: control, guided_discovery.
SRM status: pass (p=0.563703).
Primary metric automation_adoption_rate: effect 0.0 with CI [0.0, 0.0], adjusted p=1.0.
Guardrails: passed.
Decision: no_clear_evidence (primary_metric_not_statistically_or_practically_clear).
