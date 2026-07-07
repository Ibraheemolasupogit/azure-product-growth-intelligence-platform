# Power BI Dashboard Specification

This document specifies report pages and visuals for Power BI implementation.
It does not claim that a `.pbix` file or Power BI Service workspace exists.

## Page 1 - Executive Product Health

Business questions:
- overall product health
- key funnel conversion
- retention snapshot
- churn-risk model status
- experiment decision summary
- top recommended investigations
- caveats

Visuals:
- `v_health_score`: Product Health Score (card) from `fact_product_health`.
- `v_health_actions`: Recommended Investigations (table) from `fact_product_insights`.

All visuals use synthetic NexaFlow evidence.

## Page 2 - Funnel and Activation

Business questions:
- funnel stage conversion
- drop-off table
- segment comparison
- time-to-completion

Visuals:
- `v_funnel_conversion`: Funnel Conversion (bar_chart) from `fact_funnel_performance`.

All visuals use synthetic NexaFlow evidence.

## Page 3 - Retention and Cohorts

Business questions:
- retention matrix
- cohort summary
- rolling retention
- resurrection analysis

Visuals:
- `v_retention_matrix`: Cohort Return Rate (matrix) from `fact_retention`.

All visuals use synthetic NexaFlow evidence.

## Page 4 - Churn Risk

Business questions:
- model performance
- threshold trade-offs
- feature indicators
- risk-band distribution
- subgroup caveats

Visuals:
- `v_churn_performance`: Churn Model Performance (clustered_bar) from `fact_churn_model_performance`.

All visuals use synthetic NexaFlow evidence.

## Page 5 - Segmentation

Business questions:
- segment profiles
- PCA scatter specification
- segment size
- differentiators

Visuals:
- `v_segment_share`: Segment Population Share (treemap) from `fact_segment_profiles`.

All visuals use synthetic NexaFlow evidence.

## Page 6 - Recommendations

Business questions:
- model comparison
- ranking metrics
- catalogue coverage
- novelty and diversity

Visuals:
- `v_recommendation_models`: Recommendation Model Comparison (table) from `fact_recommendation_performance`.

All visuals use synthetic NexaFlow evidence.

## Page 7 - Experiments

Business questions:
- experiment decisions
- treatment effects
- guardrails
- SRM
- power limits

Visuals:
- `v_experiment_decisions`: Experiment Decisions (table) from `fact_experiment_decisions`.

All visuals use synthetic NexaFlow evidence.

## Page 8 - Governance and Lineage

Business questions:
- source evidence
- synthetic-data disclaimer
- manifests
- quality status
- lineage

Visuals:
- `v_lineage_map`: Evidence Lineage (decomposition_tree) from `dim_milestone`.

All visuals use synthetic NexaFlow evidence.

