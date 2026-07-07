# Power BI-Ready Reporting Layer

Milestone 11 adds a governed reporting handoff from committed synthetic evidence to Power BI-ready local artifacts. The layer creates compact CSV fact and dimension tables, a semantic model design, a certified metric dictionary, dashboard and visual specifications, refresh guidance, governance notes, lineage, diagnostics, and manifest checksums.

The implementation does not create `.pbix` files, connect to Power BI Service, deploy Fabric workspaces, provision Azure resources, or start Milestone 12 deployment work.

## Inputs

The reporting layer reads committed evidence from:

- `docs/evidence/milestone-4/`
- `docs/evidence/milestone-5/`
- `docs/evidence/milestone-6/`
- `docs/evidence/milestone-7/`
- `docs/evidence/milestone-8/`
- `docs/evidence/milestone-9/`
- `docs/evidence/milestone-10/`

Raw source data is not required by default.

## Outputs

Runtime outputs are written under `outputs/reporting/powerbi/<run_id>/`, which remains ignored by Git. Deterministic evidence for the portfolio sample is stored in `docs/evidence/milestone-11/`.

The star schema includes:

- `fact_product_health.csv`
- `fact_funnel_performance.csv`
- `fact_retention.csv`
- `fact_churn_model_performance.csv`
- `fact_segment_profiles.csv`
- `fact_recommendation_performance.csv`
- `fact_experiment_decisions.csv`
- `fact_product_insights.csv`
- `dim_metric.csv`
- `dim_milestone.csv`
- `dim_analysis_domain.csv`
- `dim_date.csv`

## Semantic Model

The semantic model is documented in JSON and Markdown. It records fact and dimension grains, primary keys, relationship guidance, recommended DAX-style measures, filter direction, refresh policy, row-level security guidance, sensitivity classification, and lineage back to prior milestone evidence.

Recommended filter direction is single direction from dimensions to facts. The data sensitivity classification is synthetic non-customer data.

## Azure and Power BI Mapping

| Local capability | Azure / Power BI mapping |
| --- | --- |
| Reporting CSV outputs | ADLS Gen2 curated reporting zone |
| Semantic model JSON | Power BI semantic model / Tabular model design |
| Metric dictionary | Certified Power BI metrics / governance catalogue |
| Dashboard specification | Power BI report pages |
| Refresh plan | Power BI scheduled refresh / Data Factory orchestration |
| Lineage | Microsoft Purview |
| Security guidance | Entra ID, Power BI RLS, workspace roles |
| Monitoring | Power BI refresh history, Azure Monitor |
| Source analytics | Azure Synapse / ADLS curated outputs |

## Validation

Validation checks required evidence, unique table names, unique metric IDs, stable dimension keys, documented fact grains, relationship references, visual table references, page coverage, synthetic-data flags, lineage references, manifest checksums, and absence of deployment claims.
