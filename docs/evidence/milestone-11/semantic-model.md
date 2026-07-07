# Power BI Semantic Model

This semantic model describes Power BI-ready outputs for the synthetic NexaFlow
portfolio.
No `.pbix` file, Power BI deployment, Fabric workspace, or Azure resource is created.

Model version: `2026-07-milestone-11`.
Data sensitivity: `synthetic_non_customer_data`.
Recommended filter direction: single direction from dimensions to facts.

## Tables

| Table | Type | Grain | Rows | Lineage |
| --- | --- | --- | --- | --- |
| dim_analysis_domain | dimension | analysis domain | 9 | milestone_11/reporting-model |
| dim_date | dimension | date | 1 | milestone_11/reporting-model |
| dim_metric | dimension | metric | 12 | milestone_11/reporting-model |
| dim_milestone | dimension | milestone | 8 | milestone_11/reporting-model |
| fact_churn_model_performance | fact | model split | 2 | milestone_6/evaluation-metrics.json |
| fact_experiment_decisions | fact | experiment decision | 4 | milestone_9/decision-summary.csv |
| fact_funnel_performance | fact | funnel | 6 | milestone_4/funnel-summary.csv |
| fact_product_health | fact | reporting run | 1 | milestones 4-10 |
| fact_product_insights | fact | insight | 8 | milestone_10/grounded-insights.json |
| fact_recommendation_performance | fact | recommendation model | 4 | milestone_8/model-comparison.csv |
| fact_retention | fact | retention definition and cohort period | 24 | milestone_5/cohort-summary.csv |
| fact_segment_profiles | fact | segment | 7 | milestone_7/segment-profiles.csv |

## Relationships

| From | To | Cardinality |
| --- | --- | --- |
| dim_analysis_domain | fact_product_health | one_to_many |
| dim_analysis_domain | fact_funnel_performance | one_to_many |
| dim_analysis_domain | fact_retention | one_to_many |
| dim_analysis_domain | fact_churn_model_performance | one_to_many |
| dim_analysis_domain | fact_segment_profiles | one_to_many |
| dim_analysis_domain | fact_recommendation_performance | one_to_many |
| dim_analysis_domain | fact_experiment_decisions | one_to_many |
| dim_analysis_domain | fact_product_insights | one_to_many |
| dim_date | fact_product_health | one_to_many_optional |
| dim_metric | fact_product_health | reference_documentation |

## Recommended DAX-Style Measures

### Funnel Conversion Rate

- Metric ID: `funnel_conversion_rate`
- Formula: `DIVIDE(SUM(fact_funnel_performance[completed]), SUM(fact_funnel_performance[entrants]))`
- Caveat: Descriptive synthetic funnel evidence; suppressed segment cells are excluded.

### Stage Drop-off Rate

- Metric ID: `stage_dropoff_rate`
- Formula: `DIVIDE([Prior Stage Users] - [Current Stage Users], [Prior Stage Users])`
- Caveat: Right-censored journeys remain governed by funnel diagnostics.

### Classic Retention Rate

- Metric ID: `classic_retention_rate`
- Formula: `DIVIDE(SUM(fact_retention[retained_users]), SUM(fact_retention[observed_denominator]))`
- Caveat: Right-censored periods use observed denominators.

### Rolling Retention Rate

- Metric ID: `rolling_retention_rate`
- Formula: `DIVIDE(SUM(fact_retention[rolling_retained_users]), SUM(fact_retention[observed_denominator]))`
- Caveat: Synthetic cohort sizes are small.

### Churn Precision

- Metric ID: `churn_precision`
- Formula: `AVERAGE(fact_churn_model_performance[precision])`
- Caveat: Risk indicator only; not for automated adverse decisions.

### Churn Recall

- Metric ID: `churn_recall`
- Formula: `AVERAGE(fact_churn_model_performance[recall])`
- Caveat: Selected threshold is validation-driven.

### Segment Population Share

- Metric ID: `segment_population_share`
- Formula: `SUM(fact_segment_profiles[user_count]) / CALCULATE(SUM(fact_segment_profiles[user_count]), ALL(fact_segment_profiles))`
- Caveat: Segment labels are analytical interpretations.

### Recommendation NDCG@5

- Metric ID: `recommendation_ndcg_at_5`
- Formula: `AVERAGE(fact_recommendation_performance[ndcg_at_5])`
- Caveat: Offline ranking metric, not a probability.

### Experiment Treatment Effect

- Metric ID: `experiment_treatment_effect`
- Formula: `AVERAGE(fact_experiment_decisions[estimated_effect])`
- Caveat: Decision also depends on power, SRM, integrity, and guardrails.

### Guardrail Failure Count

- Metric ID: `guardrail_failure_count`
- Formula: `COUNTROWS(FILTER(fact_experiment_decisions, fact_experiment_decisions[guardrail_status] = "fail"))`
- Caveat: Guardrails can block rollout even when primary metric improves.

### Insight Governance Pass Rate

- Metric ID: `insight_governance_pass_rate`
- Formula: `See metric dictionary definition.`
- Caveat: Checks validate grounding and language constraints, not business truth.

### Data Quality Status

- Metric ID: `data_quality_status`
- Formula: `See metric dictionary definition.`
- Caveat: Local deterministic validation; no Power BI deployment is performed.

## Security and Refresh

Use workspace roles for synthetic demonstration access. For real tenant use, review
domain, geography, and customer ownership filters before enabling row-level security.
Refresh should rebuild the reporting layer from certified evidence and compare
manifest checksums before publishing semantic-model changes.

