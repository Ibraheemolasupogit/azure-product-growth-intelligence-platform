# Metric Framework

This document defines governed metric concepts. Milestone 4 implements operational funnel formulas and denominator rules for descriptive product journeys. Milestone 6 adds governed churn-model evaluation definitions.

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

## Operational Retention Metrics

| Metric ID | Business meaning | Numerator | Denominator | Grain | Time grain | Null handling |
| --- | --- | --- | --- | --- | --- | --- |
| `RETENTION_COHORT_SIZE` | Users assigned to a cohort | Cohort members | Not applicable | Definition-cohort period | Daily, weekly, monthly | Zero when no users qualify |
| `RETENTION_OBSERVED_DENOMINATOR` | Users whose full period is observable | Observed users | Cohort size | Definition-cohort-period | Daily, weekly, monthly | Zero when fully censored |
| `RETENTION_CLASSIC_RATE` | Users active specifically in period N | Retained users in period N | Observed denominator | Definition-cohort-period | Daily, weekly, monthly | Null when denominator is zero or suppressed |
| `RETENTION_ROLLING_RATE` | Users active in period N or later observed periods | Rolling retained users | Observed denominator | Definition-cohort-period | Daily, weekly, monthly | Null when denominator is zero or suppressed |
| `RETENTION_RETURN_RATE` | Users returning after period 0 | Users active after anchor period | Cohort size | Definition-cohort | Daily, weekly, monthly | Null when cohort is empty |
| `RETENTION_ACTIVE_USER_RATE` | Active users in each observed period | Active users | Observed denominator | Definition-cohort-period | Daily, weekly, monthly | Null when denominator is zero or suppressed |
| `RETENTION_CENSORED_USERS` | Users excluded because a period is incomplete | Cohort size minus observed denominator | Cohort size | Definition-cohort-period | Daily, weekly, monthly | Zero when fully observed |
| `RETENTION_INACTIVE_USERS` | Users with no qualifying observed activity | Inactive users | Cohort size | Definition-cohort | Daily, weekly, monthly | Zero when none |
| `RETENTION_RESURRECTED_USERS` | Users active after prior inactivity | Resurrected users | Inactive users | Definition-cohort | Daily, weekly, monthly | Zero when none |
| `RETENTION_RESURRECTION_RATE` | Share of inactive users who return | Resurrected users | Inactive users | Definition-cohort | Daily, weekly, monthly | Null when denominator is zero |
| `RETENTION_MEDIAN_DAYS_TO_FIRST_RETURN` | Typical time from anchor to first return | Days to first post-anchor active period | Returning users | Definition-cohort | Daily, weekly, monthly | Null when no users return |

Retention metrics use trusted accepted event time, explicit cohort anchors, meaningful qualifying activity, observed denominators, right-censoring, and privacy-aware suppression. Churn-like lifecycle status is descriptive and must not be used as a predictive churn label.

## Churn Model Metrics

| Metric ID | Business meaning | Definition | Null handling |
| --- | --- | --- | --- |
| `CHURN_PREVALENCE` | Share of labelled snapshots that churn | Positive behavioural churn labels divided by labelled snapshots | Zero when no rows exist |
| `CHURN_ACCURACY` | Overall classification correctness | Correct thresholded predictions divided by scored rows | Null when no rows exist |
| `CHURN_BALANCED_ACCURACY` | Mean recall across churn and non-churn classes | Average of sensitivity and specificity | Null when a split has one class |
| `CHURN_PRECISION` | Share of flagged users who churn | True positives divided by predicted positives | Zero when none are flagged |
| `CHURN_RECALL` | Share of churners captured | True positives divided by actual positives | Zero when no positives exist |
| `CHURN_F1` | Precision-recall balance | Harmonic mean of precision and recall | Zero when precision and recall are zero |
| `CHURN_ROC_AUC` | Ranking quality across thresholds | Area under ROC curve | Null when a split has one class |
| `CHURN_AVERAGE_PRECISION` | Precision-recall ranking quality | Average precision over ranked probabilities | Null when a split has one class |
| `CHURN_BRIER_SCORE` | Probability calibration loss | Mean squared probability error | Null when no rows exist |
| `CHURN_LOG_LOSS` | Probabilistic classification loss | Binary cross-entropy with labels `[0, 1]` | Null when a split has one class |
| `CHURN_TOP_DECILE_PRECISION` | Workload-focused capture quality | Precision among highest-risk 10 percent | Zero when no positives exist |
| `CHURN_TOP_20_RECALL` | Capacity-based recall | Recall among highest-risk 20 percent | Zero when no positives exist |

Churn model selection uses validation metrics only. The default rule ranks by validation average precision, then Brier score, with logistic regression preferred on ties for interpretability. The held-out test split is reported only after model and threshold selection.

## Segmentation Quality Metrics

| Metric ID | Business meaning | Definition | Null handling |
| --- | --- | --- | --- |
| `SEGMENT_SILHOUETTE` | Cluster separation and cohesion | Mean silhouette score over scaled clustering features | Null when fewer than two clusters exist |
| `SEGMENT_DAVIES_BOULDIN` | Lower-is-better cluster separation | Average similarity between each cluster and its nearest neighbour | Null when fewer than two clusters exist |
| `SEGMENT_CALINSKI_HARABASZ` | Between-cluster dispersion versus within-cluster dispersion | Variance-ratio criterion over scaled features | Null when fewer than two clusters exist |
| `SEGMENT_STABILITY_ARI` | Assignment robustness across deterministic seeds | Adjusted Rand index versus reference seed | Null when comparison labels cannot be produced |
| `SEGMENT_MIN_CLUSTER_SIZE` | Smallest selected cluster | Minimum assignment count across clusters | Zero when no assignments exist |
| `SEGMENT_PROFILE_SHARE` | Segment population share | Segment users divided by eligible users | Null when no eligible users exist |

Segmentation candidates are selected by rejecting clusters below the minimum-size rule, prioritising silhouette score, using stability as a tie-breaker, and preferring fewer clusters where quality is materially similar. Segment profiles are descriptive and suppression-aware.
