# Churn Prediction Model Card

This model is a deterministic demonstration over synthetic NexaFlow data.

- Primary target: behavioural churn over 28 days.
- Snapshot design: 28-day point-in-time lookback, then future label window.
- Selected model: logistic.
- Selected threshold: 0.3.
- Validation F1: 1.0.
- Test F1: 1.0.

Predictions are probabilistic and feature importance is associative, not causal.
This model must not be used for automated adverse decisions.

Recommended next investigations: validate on larger samples, review
fairness-sensitive
subgroups, monitor drift, and compare interventions through governed experiments.
