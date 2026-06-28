# Metric Framework

This document defines planned metric concepts. Exact operational formulas, tests, and denominator rules will be implemented in later milestones.

| Metric | Conceptual definition |
| --- | --- |
| Active users | Users with qualifying product activity in an observation window |
| Session frequency | Number of sessions per active user over a defined window |
| Engagement rate | Share of eligible users performing one or more meaningful engagement events |
| Feature adoption | Share of eligible users who use a feature after it becomes available |
| Funnel entry | Users or sessions that begin a defined journey |
| Funnel completion | Users or sessions that reach the terminal success event |
| Conversion rate | Funnel completions divided by valid funnel entries |
| Drop-off rate | Funnel entries that fail to reach a later step within the window |
| Retention | Users active in a later period after qualifying in a starting cohort |
| Churn | Previously active or subscribed users who become inactive or cancelled |
| Resurrection | Previously churned or inactive users who return to qualifying activity |
| Customer lifetime value | Expected or observed value attributed to a user relationship |
| Experiment exposure | Users who were both assigned to and exposed to an experiment condition |
| Treatment effect | Difference between treatment and control outcomes with uncertainty |
| Recommendation interaction | User impressions, clicks, accepts, dismissals, or conversions from recommendations |
| Feedback sentiment | Polarity or theme signal derived from feedback text |

## Governance Rules

Metric owners should define denominators, inclusion criteria, observation windows, and event-time handling before metrics are published. The same business metric should not be recomputed with conflicting logic in multiple modules.

Event-time handling should prefer source event timestamps for behavioural analysis, with ingestion timestamps used for operational monitoring. Late-arriving events, duplicate events, and user identity changes must be handled explicitly in later implementations.

Experiment metrics require pre-defined eligibility, exposure, outcome windows, guardrails, and practical significance thresholds. GenAI summaries must cite grounded metric outputs rather than inventing formulas.

