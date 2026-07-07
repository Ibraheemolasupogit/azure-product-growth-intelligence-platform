"""Semantic model metadata and Markdown documentation."""

from __future__ import annotations

from typing import Any, cast

from product_growth_intelligence.reporting.metric_dictionary import METRIC_DICTIONARY
from product_growth_intelligence.reporting.tables import ReportingTables
from product_growth_intelligence.reporting.writers import markdown_table


def build_semantic_model(tables: ReportingTables) -> dict[str, object]:
    """Build a documented star-schema semantic model."""

    fact_tables = [name for name in tables if name.startswith("fact_")]
    return {
        "model_name": "NexaFlow Product Growth Reporting Semantic Model",
        "model_version": "2026-07-milestone-11",
        "description": "Power BI-ready semantic layer over committed synthetic evidence.",
        "data_sensitivity": "synthetic_non_customer_data",
        "refresh_policy": {
            "mode": "deterministic_local_build",
            "recommended_powerbi_mapping": "scheduled refresh from curated ADLS Gen2 exports",
        },
        "row_level_security": {
            "recommended_role": "ProductLeadershipViewer",
            "filter_guidance": (
                "Use workspace roles first; add domain or region RLS only after real tenant review."
            ),
        },
        "tables": [
            {
                "name": name,
                "type": "fact" if name in fact_tables else "dimension",
                "grain": _grain(name),
                "primary_key": "stable_id" if name.startswith("fact_") else _dimension_key(name),
                "row_count": len(rows),
                "synthetic_data_flag": True,
                "lineage": _lineage(name),
            }
            for name, rows in sorted(tables.items())
        ],
        "relationships": _relationships(),
        "measures": _measures(),
        "filter_direction": "single direction from dimensions to facts",
        "lineage": {
            "source_milestones": [4, 5, 6, 7, 8, 9, 10],
            "reporting_milestone": 11,
        },
    }


def semantic_model_markdown(model: dict[str, object]) -> list[str]:
    """Render semantic model documentation."""

    model_tables = cast("list[dict[str, Any]]", model["tables"])
    model_relationships = cast("list[dict[str, Any]]", model["relationships"])
    tables = [
        {
            "Table": table["name"],
            "Type": table["type"],
            "Grain": table["grain"],
            "Rows": table["row_count"],
            "Lineage": table["lineage"],
        }
        for table in model_tables
    ]
    relationships = [
        {
            "From": relationship["from_table"],
            "To": relationship["to_table"],
            "Cardinality": relationship["cardinality"],
        }
        for relationship in model_relationships
    ]
    lines = [
        "# Power BI Semantic Model",
        "",
        "This semantic model describes Power BI-ready outputs for the synthetic NexaFlow",
        "portfolio.",
        "No `.pbix` file, Power BI deployment, Fabric workspace, or Azure resource is created.",
        "",
        f"Model version: `{model['model_version']}`.",
        f"Data sensitivity: `{model['data_sensitivity']}`.",
        "Recommended filter direction: single direction from dimensions to facts.",
        "",
        "## Tables",
        "",
        *markdown_table(tables, ["Table", "Type", "Grain", "Rows", "Lineage"]),
        "",
        "## Relationships",
        "",
        *markdown_table(relationships, ["From", "To", "Cardinality"]),
        "",
        "## Recommended DAX-Style Measures",
        "",
    ]
    for measure in cast("list[dict[str, Any]]", model["measures"]):
        if isinstance(measure, dict):
            lines.extend(
                [
                    f"### {measure['name']}",
                    "",
                    f"- Metric ID: `{measure['metric_id']}`",
                    f"- Formula: `{measure['formula']}`",
                    f"- Caveat: {measure['caveat']}",
                    "",
                ]
            )
    lines.extend(
        [
            "## Security and Refresh",
            "",
            "Use workspace roles for synthetic demonstration access. For real tenant use, review",
            "domain, geography, and customer ownership filters before enabling row-level security.",
            "Refresh should rebuild the reporting layer from certified evidence and compare",
            "manifest checksums before publishing semantic-model changes.",
            "",
        ]
    )
    return lines


def _relationships() -> list[dict[str, str]]:
    facts = [
        "fact_product_health",
        "fact_funnel_performance",
        "fact_retention",
        "fact_churn_model_performance",
        "fact_segment_profiles",
        "fact_recommendation_performance",
        "fact_experiment_decisions",
        "fact_product_insights",
    ]
    relationships = [
        {
            "from_table": "dim_analysis_domain",
            "from_field": "domain_key",
            "to_table": fact,
            "to_field": "domain_key",
            "cardinality": "one_to_many",
        }
        for fact in facts
    ]
    relationships.extend(
        [
            {
                "from_table": "dim_date",
                "from_field": "date_key",
                "to_table": "fact_product_health",
                "to_field": "reporting_date_key",
                "cardinality": "one_to_many_optional",
            },
            {
                "from_table": "dim_metric",
                "from_field": "metric_id",
                "to_table": "fact_product_health",
                "to_field": "metric_id",
                "cardinality": "reference_documentation",
            },
        ]
    )
    return relationships


def _measures() -> list[dict[str, str]]:
    formulas = {
        "funnel_conversion_rate": (
            "DIVIDE(SUM(fact_funnel_performance[completed]), "
            "SUM(fact_funnel_performance[entrants]))"
        ),
        "stage_dropoff_rate": (
            "DIVIDE([Prior Stage Users] - [Current Stage Users], [Prior Stage Users])"
        ),
        "classic_retention_rate": (
            "DIVIDE(SUM(fact_retention[retained_users]), SUM(fact_retention[observed_denominator]))"
        ),
        "rolling_retention_rate": (
            "DIVIDE(SUM(fact_retention[rolling_retained_users]), "
            "SUM(fact_retention[observed_denominator]))"
        ),
        "churn_precision": "AVERAGE(fact_churn_model_performance[precision])",
        "churn_recall": "AVERAGE(fact_churn_model_performance[recall])",
        "segment_population_share": (
            "SUM(fact_segment_profiles[user_count]) / "
            "CALCULATE(SUM(fact_segment_profiles[user_count]), ALL(fact_segment_profiles))"
        ),
        "recommendation_ndcg_at_5": "AVERAGE(fact_recommendation_performance[ndcg_at_5])",
        "experiment_treatment_effect": "AVERAGE(fact_experiment_decisions[estimated_effect])",
        "guardrail_failure_count": (
            "COUNTROWS(FILTER(fact_experiment_decisions, "
            'fact_experiment_decisions[guardrail_status] = "fail"))'
        ),
    }
    return [
        {
            "metric_id": str(metric["metric_id"]),
            "name": str(metric["metric_name"]),
            "formula": formulas.get(str(metric["metric_id"]), "See metric dictionary definition."),
            "caveat": str(metric["caveats"]),
        }
        for metric in METRIC_DICTIONARY
    ]


def _grain(table_name: str) -> str:
    grains = {
        "fact_product_health": "reporting run",
        "fact_funnel_performance": "funnel",
        "fact_retention": "retention definition and cohort period",
        "fact_churn_model_performance": "model split",
        "fact_segment_profiles": "segment",
        "fact_recommendation_performance": "recommendation model",
        "fact_experiment_decisions": "experiment decision",
        "fact_product_insights": "insight",
        "dim_metric": "metric",
        "dim_milestone": "milestone",
        "dim_analysis_domain": "analysis domain",
        "dim_date": "date",
    }
    return grains[table_name]


def _lineage(table_name: str) -> str:
    lineage = {
        "fact_product_health": "milestones 4-10",
        "fact_funnel_performance": "milestone_4/funnel-summary.csv",
        "fact_retention": "milestone_5/cohort-summary.csv",
        "fact_churn_model_performance": "milestone_6/evaluation-metrics.json",
        "fact_segment_profiles": "milestone_7/segment-profiles.csv",
        "fact_recommendation_performance": "milestone_8/model-comparison.csv",
        "fact_experiment_decisions": "milestone_9/decision-summary.csv",
        "fact_product_insights": "milestone_10/grounded-insights.json",
    }
    return lineage.get(table_name, "milestone_11/reporting-model")


def _dimension_key(table_name: str) -> str:
    keys = {
        "dim_metric": "metric_id",
        "dim_milestone": "milestone_key",
        "dim_analysis_domain": "domain_key",
        "dim_date": "date_key",
    }
    return keys[table_name]
