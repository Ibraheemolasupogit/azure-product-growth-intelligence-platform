# Executive Experiment Report

Objective: evaluate synthetic NexaFlow controlled experiments with governed
integrity checks, treatment effects, uncertainty, guardrails and decisions.

All data is synthetic. Offline experiment analysis does not prove external
validity, small samples may be underpowered, and subgroup analyses are
exploratory. Decisions require product, data and risk stakeholder review.

- Experiments analysed: 4.
- Overall status: passed_with_warnings.
- Valid assignments: 12.
- SRM findings: 0.
- Guardrail failures: 2.
- Suppressed segment tests: 47.
- Strongest positive primary effect: exp_simplified_onboarding (0.5).
- Strongest negative primary effect: exp_template_recommendation (0.0).

Decisions:
- exp_simplified_onboarding: do_not_ship (critical_guardrail_harm).
- exp_template_recommendation: do_not_ship (critical_guardrail_harm).
- exp_trial_upgrade_prompt: no_clear_evidence (primary_metric_not_statistically_or_practically_clear).
- exp_automation_discovery: no_clear_evidence (primary_metric_not_statistically_or_practically_clear).

Recommended next actions: increase sample sizes, investigate guardrail
failures before rollout, preserve fixed-window analysis discipline, and
treat segment findings as exploratory until adequately powered.
