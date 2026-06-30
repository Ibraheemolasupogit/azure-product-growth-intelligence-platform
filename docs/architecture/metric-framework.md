# Metric Framework

This document defines governed metric concepts. Milestone 4 implements operational funnel formulas and denominator rules for descriptive product journeys.

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

## Operational Funnel Metrics

| Metric ID | Business meaning | Numerator | Denominator | Grain | Unit | Null handling |
| --- | --- | --- | --- | --- | --- | --- |
| `FUNNEL_ELIGIBLE_USERS` | Users eligible for a governed funnel | Eligible users | Not applicable | User-funnel | Count | Zero when none qualify |
| `FUNNEL_ENTRANTS` | Eligible users who start the funnel | Users with entry stage | Eligible users | User-funnel | Count | Zero when none enter |
| `FUNNEL_ENTRY_RATE` | Share of eligible users who enter | Entrants | Eligible users | User-funnel | Proportion | Null when denominator is zero |
| `FUNNEL_STAGE_REACH_RATE` | Share reaching a stage | Users reaching stage | Eligible users or entrants | User-funnel-stage | Proportion | Null when denominator is zero |
| `FUNNEL_STEP_CONVERSION_RATE` | Share moving from prior stage to current stage | Users reaching current stage | Users reaching previous stage | User-funnel-stage | Proportion | Null when denominator is zero |
| `FUNNEL_CUMULATIVE_CONVERSION_RATE` | Share of eligible users reaching a stage | Users reaching stage | Eligible users | User-funnel-stage | Proportion | Null when denominator is zero |
| `FUNNEL_DROPOFF_RATE` | Share of prior-stage users not reaching the next stage | Prior-stage users minus current-stage users | Prior-stage users | User-funnel-stage | Proportion | Null when denominator is zero |
| `FUNNEL_COMPLETION_RATE` | Share of eligible users completing the funnel | Completed attempts | Eligible users | User-funnel | Proportion | Null when denominator is zero |
| `FUNNEL_FULLY_OBSERVED_CONVERSION_RATE` | Completion rate excluding censored attempts | Completed attempts | Entrants minus censored attempts | User-funnel | Proportion | Null when denominator is zero |
| `FUNNEL_MEDIAN_TIME_TO_COMPLETE` | Typical elapsed time from entry to completion | Completed attempt durations | Completed attempts | User-funnel | Seconds | Null when no completions exist |
| `FUNNEL_CENSORED_ATTEMPTS` | Attempts whose completion window extends past analysis end | Censored attempts | Entrants | User-funnel | Count | Zero when none are censored |

Funnel metrics use source event timestamps, UTC timestamp parsing, deterministic event ordering, first-entry attempts, explicit completion windows, and right-censoring. Segment metrics are descriptive and privacy-aware; suppressed cells are omitted from segment output and listed in diagnostics.
