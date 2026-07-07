# Metric Framework

This document defines governed metric concepts. Milestone 4 implements operational funnel formulas and denominator rules for descriptive product journeys. Milestone 6 adds governed churn-model evaluation definitions. Milestone 8 adds offline recommendation-ranking metric definitions. Milestone 9 adds governed experiment-analysis metric definitions. Milestone 10 adds deterministic insight-governance checks. Milestone 11 publishes a unified reporting metric dictionary for Power BI-ready semantic documentation.

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

## Recommendation Ranking Metrics

| Metric ID | Business meaning | Definition | Null handling |
| --- | --- | --- | --- |
| `REC_PRECISION_AT_K` | Share of top-K recommendations that appear in future holdout interactions | Relevant recommended items in top K divided by recommended items in top K | Zero when no evaluated recommendations exist |
| `REC_RECALL_AT_K` | Share of future relevant items captured in top K | Relevant recommended items in top K divided by relevant holdout items | Zero when no relevant holdout items exist |
| `REC_HIT_RATE_AT_K` | Share of evaluated users with at least one relevant top-K recommendation | Users with a hit in top K divided by evaluated users | Zero when no evaluated users exist |
| `REC_MRR` | Ranking position of first relevant recommendation | Mean reciprocal rank of first hit per evaluated user | Zero when no first hit exists |
| `REC_MAP_AT_K` | Average precision across the ranked top-K list | Mean average precision at K over evaluated users | Zero when no evaluated users exist |
| `REC_NDCG_AT_K` | Position-aware ranking quality | Normalised discounted cumulative gain at K against binary holdout relevance | Zero when ideal DCG is zero |
| `REC_CATALOGUE_COVERAGE_AT_K` | Breadth of catalogue exposure | Distinct items recommended in top K divided by active catalogue items | Zero when catalogue is empty |
| `REC_USER_COVERAGE` | Share of eligible users receiving recommendations | Users with recommendation rows divided by eligible users with model output | Zero when no eligible users exist |
| `REC_NOVELTY_AT_K` | Preference for less historically common items | Mean negative log historical item share with smoothing | Zero when no recommendation rows exist |
| `REC_DIVERSITY_AT_K` | Variety of item categories within recommendation lists | Mean distinct item categories divided by recommended items | Zero when no recommendation rows exist |
| `REC_FALLBACK_RATE` | Share of recommendations produced by fallback logic | Fallback recommendation rows divided by recommendation rows | Zero when no recommendation rows exist |

Recommendation metrics are descriptive offline metrics over synthetic data. The future holdout window is used only for evaluation and never for candidate generation or scoring. Model selection rejects models below coverage guardrails, prioritises NDCG@5, uses recall@5 as a tie-breaker, and prefers simpler baselines where quality is materially similar.

## Experiment Analysis Metrics

| Metric ID | Business meaning | Definition | Null handling |
| --- | --- | --- | --- |
| `EXP_CONTROL_VALUE` | Control-arm metric value | Control rate, mean, or count-per-user depending on metric type | Zero when the control sample is empty |
| `EXP_TREATMENT_VALUE` | Treatment-arm metric value | Treatment rate, mean, or count-per-user depending on metric type | Zero when the treatment sample is empty |
| `EXP_ABSOLUTE_EFFECT` | Treatment effect in metric units | Treatment value minus control value | Zero when both arms are empty |
| `EXP_RELATIVE_EFFECT` | Relative treatment effect | Absolute effect divided by control value | Zero when control value is zero |
| `EXP_RISK_RATIO` | Binary treatment/control rate ratio | Treatment rate divided by control rate | Zero when control rate is zero |
| `EXP_ODDS_RATIO` | Binary odds-ratio estimate | Haldane-Anscombe corrected odds ratio | Reported as zero for non-binary metrics |
| `EXP_CONFIDENCE_INTERVAL` | Uncertainty interval for treatment effect | Normal-approximation risk-difference interval for binary metrics; Welch interval for continuous and count means | Bounds equal zero when standard error is zero |
| `EXP_P_VALUE` | Statistical test p-value | Two-proportion z-test for binary metrics; Welch's t-test for continuous and count metrics | One when the test is unavailable |
| `EXP_ADJUSTED_P_VALUE` | Multiple-testing adjusted p-value | `none`, `bonferroni`, or `benjamini_hochberg` correction by configured family | Same as raw p-value when correction is `none` |
| `EXP_SRM_P_VALUE` | Sample-ratio mismatch evidence | Chi-square goodness-of-fit p-value against planned allocation | One when expected counts are unavailable |
| `EXP_REQUIRED_SAMPLE_SIZE` | Planning sample size | Normal-approximation binary sample size per variant from baseline rate, MDE, alpha and target power | Zero when MDE is invalid |
| `EXP_GUARDRAIL_STATUS` | Whether a guardrail blocks rollout | Fail when critical harm exceeds configured threshold | Pass when no critical harm is detected |
| `EXP_DECISION` | Deterministic decision state | Combines integrity, SRM, primary metric, practical significance, power and guardrails | `invalid_experiment` when integrity or SRM blocks confidence |

Experiment metrics use fixed analysis windows. Intention-to-treat is the primary population; exposed analysis is secondary. Statistical significance alone is insufficient for a ship decision: practical thresholds, sample sufficiency, SRM, integrity and guardrails are also required. Segment effects are exploratory and suppressed when either arm is below the configured segment threshold.

## Product Insight Governance Checks

| Check ID | Business meaning | Passing condition |
| --- | --- | --- |
| `INSIGHT_SOURCE_COVERAGE` | Every generated insight is auditable | Each insight cites at least one loaded local evidence artifact |
| `INSIGHT_SYNTHETIC_DISCLOSURE` | Reports retain synthetic-data caveats | Every insight and report includes the synthetic-data disclaimer |
| `INSIGHT_NO_LIVE_LLM_CALL` | Local-first deterministic operation | Prompt package records `llm_call_performed=false` |
| `INSIGHT_CAUSAL_LANGUAGE_BLOCK` | Unsupported causal claims are avoided | Blocked causal terms are absent unless explicitly supported |
| `INSIGHT_CHURN_CERTAINTY_BLOCK` | Churn output remains probabilistic/risk-oriented | Churn insights avoid certainty claims |
| `INSIGHT_RECOMMENDATION_PROBABILITY_BLOCK` | Recommendation outputs are not overclaimed | Recommendation insights describe rankings, not probabilities |
| `INSIGHT_SEGMENT_CAVEAT` | Segment labels remain interpretive | Segmentation insights include analytical-interpretation caveats |
| `INSIGHT_EXPERIMENT_CAVEAT` | Experiment conclusions remain governed | Experiment insights include sample-size and guardrail caveats |

Insight checks are binary governance controls, not product KPIs. A failed governance check fails the assistant run.

## Reporting Metric Dictionary

Milestone 11 writes `metric-dictionary.csv` as the reporting handoff definition source. It covers funnel conversion and drop-off, retention, churn precision and recall, segment population share, recommendation NDCG@5, experiment treatment effect, guardrail failures, insight governance, and data-quality status.

The dictionary records business and technical definitions, numerator, denominator, unit, aggregation behaviour, grain, source domain, source artifact, owner role, caveats, and synthetic-data flag. Power BI measures should refer back to this dictionary before publication.
