# Executive Funnel Report

Scope: governed funnel analytics over trusted Milestone 3 accepted datasets.

All data is synthetic. Findings are descriptive, associations are not causal, and small-sample evidence is illustrative.

## Major Funnel Results
- account_activation: 0/12 eligible users completed; entry rate 0.083333; status passed.
- automation_adoption: 0/1 eligible users completed; entry rate 1.0; status passed.
- collaboration_adoption: 0/8 eligible users completed; entry rate 1.0; status passed.
- onboarding: 0/12 eligible users completed; entry rate 1.0; status passed.
- recommendation_interaction: 1/7 eligible users completed; entry rate 1.0; status passed.
- trial_to_paid: 0/12 eligible users completed; entry rate 1.0; status passed.

## Largest Stage Drop-Offs
- trial_to_paid / trial_started: 12 users dropped before reaching this stage.
- onboarding / workspace_created: 9 users dropped before reaching this stage.
- collaboration_adoption / project_created: 8 users dropped before reaching this stage.
- recommendation_interaction / recommendation_accepted: 4 users dropped before reaching this stage.
- onboarding / onboarding_completed: 3 users dropped before reaching this stage.

## Drop-Off Diagnostics
- account_activation: 1 attempts stopped after onboarding_completed; next expected workspace_created.
- automation_adoption: 1 attempts stopped after automation_executed; next expected repeated_automation_use.
- collaboration_adoption: 8 attempts stopped after workspace_created; next expected project_created.
- onboarding: 3 attempts stopped after onboarding_step_completed; next expected onboarding_completed.
- onboarding: 9 attempts stopped after onboarding_completed; next expected workspace_created.
- recommendation_interaction: 2 attempts stopped after recommendation_shown; next expected recommendation_clicked.
- recommendation_interaction: 4 attempts stopped after recommendation_clicked; next expected recommendation_accepted.
- trial_to_paid: 12 attempts stopped after upgrade_prompt_viewed; next expected trial_started.

## Caveats

- Experiment variants are descriptive slices only; no significance or uplift is calculated.
- Funnel outputs do not implement retention, churn, segmentation models, recommendations, GenAI, or Power BI.
- Diagnostics status: passed.
