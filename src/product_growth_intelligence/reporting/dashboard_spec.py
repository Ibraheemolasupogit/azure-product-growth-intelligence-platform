"""Dashboard and visual specifications for the reporting layer."""

from __future__ import annotations


def build_dashboard_pages() -> list[dict[str, object]]:
    """Return deterministic dashboard page specifications."""

    pages = [
        (
            "executive_product_health",
            "Executive Product Health",
            [
                "overall product health",
                "key funnel conversion",
                "retention snapshot",
                "churn-risk model status",
                "experiment decision summary",
                "top recommended investigations",
                "caveats",
            ],
        ),
        (
            "funnel_and_activation",
            "Funnel and Activation",
            [
                "funnel stage conversion",
                "drop-off table",
                "segment comparison",
                "time-to-completion",
            ],
        ),
        (
            "retention_and_cohorts",
            "Retention and Cohorts",
            ["retention matrix", "cohort summary", "rolling retention", "resurrection analysis"],
        ),
        (
            "churn_risk",
            "Churn Risk",
            [
                "model performance",
                "threshold trade-offs",
                "feature indicators",
                "risk-band distribution",
                "subgroup caveats",
            ],
        ),
        (
            "segmentation",
            "Segmentation",
            ["segment profiles", "PCA scatter specification", "segment size", "differentiators"],
        ),
        (
            "recommendations",
            "Recommendations",
            ["model comparison", "ranking metrics", "catalogue coverage", "novelty and diversity"],
        ),
        (
            "experiments",
            "Experiments",
            ["experiment decisions", "treatment effects", "guardrails", "SRM", "power limits"],
        ),
        (
            "governance_and_lineage",
            "Governance and Lineage",
            [
                "source evidence",
                "synthetic-data disclaimer",
                "manifests",
                "quality status",
                "lineage",
            ],
        ),
    ]
    return [
        {
            "page_id": page_id,
            "page_name": name,
            "sort_order": index,
            "business_questions": questions,
            "synthetic_data_disclaimer": "All visuals use synthetic NexaFlow evidence.",
        }
        for index, (page_id, name, questions) in enumerate(pages, start=1)
    ]


def build_visual_specs() -> list[dict[str, object]]:
    """Return machine-readable visual specifications."""

    specs = [
        _visual(
            "Executive Product Health",
            "v_health_score",
            "Product Health Score",
            "card",
            "fact_product_health",
            ["product_health_score"],
            ["Product Health Score"],
            "none",
            "descending by product_health_score",
            "amber below 0.5",
            "Is the portfolio health signal improving enough to prioritise scale?",
            "Composite score is a deterministic synthetic summary, not an official KPI.",
        ),
        _visual(
            "Executive Product Health",
            "v_health_actions",
            "Recommended Investigations",
            "table",
            "fact_product_insights",
            ["title", "priority", "owner_role"],
            ["Insight Count"],
            "priority in high, medium",
            "priority then owner_role",
            "high priority highlighted",
            "Which evidence-grounded actions should leaders inspect first?",
            "Assistant outputs are deterministic summaries with cited evidence.",
        ),
        _visual(
            "Funnel and Activation",
            "v_funnel_conversion",
            "Funnel Conversion",
            "bar_chart",
            "fact_funnel_performance",
            ["display_name", "overall_conversion_rate"],
            ["Funnel Conversion Rate"],
            "status equals passed",
            "overall_conversion_rate ascending",
            "red below 0.1",
            "Where do product journeys fail to complete?",
            "Small synthetic denominators can exaggerate rates.",
        ),
        _visual(
            "Retention and Cohorts",
            "v_retention_matrix",
            "Cohort Return Rate",
            "matrix",
            "fact_retention",
            ["definition_id", "cohort_period", "return_rate"],
            ["Classic Retention Rate", "Rolling Retention Rate"],
            "status equals passed",
            "cohort_period ascending",
            "green high return_rate",
            "Which cohorts return after their anchor period?",
            "Right-censoring and small cohorts remain visible caveats.",
        ),
        _visual(
            "Churn Risk",
            "v_churn_performance",
            "Churn Model Performance",
            "clustered_bar",
            "fact_churn_model_performance",
            ["split", "precision", "recall", "f1"],
            ["Churn Precision", "Churn Recall"],
            "split in validation,test",
            "split ascending",
            "blue for validation, grey for test",
            "How strong is the risk model on governed splits?",
            "Risk scores must not drive automated adverse decisions.",
        ),
        _visual(
            "Segmentation",
            "v_segment_share",
            "Segment Population Share",
            "treemap",
            "fact_segment_profiles",
            ["display_name", "population_share", "suppression_status"],
            ["Segment Population Share"],
            "none",
            "population_share descending",
            "suppressed segments hatched",
            "Which behavioural groups dominate the synthetic portfolio?",
            "Segment names are interpretive and non-causal.",
        ),
        _visual(
            "Recommendations",
            "v_recommendation_models",
            "Recommendation Model Comparison",
            "table",
            "fact_recommendation_performance",
            ["display_name", "ndcg_at_5", "recall_at_5", "selected_status"],
            ["Recommendation NDCG@5"],
            "none",
            "selected_status then ndcg_at_5 descending",
            "selected model highlighted",
            "Which offline recommendation baseline should be investigated further?",
            "Offline ranking metrics are not user-facing probabilities.",
        ),
        _visual(
            "Experiments",
            "v_experiment_decisions",
            "Experiment Decisions",
            "table",
            "fact_experiment_decisions",
            ["display_name", "decision", "estimated_effect", "guardrail_status"],
            ["Experiment Treatment Effect", "Guardrail Failure Count"],
            "none",
            "decision then display_name",
            "failed guardrails red",
            "Which product changes are blocked, inconclusive, or candidates for rollout?",
            "Power and guardrails can override metric direction.",
        ),
        _visual(
            "Governance and Lineage",
            "v_lineage_map",
            "Evidence Lineage",
            "decomposition_tree",
            "dim_milestone",
            ["milestone_key", "display_name", "status"],
            ["Data Quality Status"],
            "status equals completed",
            "milestone_number ascending",
            "synthetic evidence badge",
            "Which evidence artifacts feed the reporting model?",
            "This is a specification, not a deployed Power BI lineage view.",
        ),
    ]
    return specs


def dashboard_markdown(
    pages: list[dict[str, object]], visuals: list[dict[str, object]]
) -> list[str]:
    """Render readable dashboard documentation."""

    lines = [
        "# Power BI Dashboard Specification",
        "",
        "This document specifies report pages and visuals for Power BI implementation.",
        "It does not claim that a `.pbix` file or Power BI Service workspace exists.",
        "",
    ]
    for page in pages:
        page_visuals = [visual for visual in visuals if visual["page_name"] == page["page_name"]]
        lines.extend([f"## Page {page['sort_order']} - {page['page_name']}", ""])
        lines.append("Business questions:")
        questions = page["business_questions"]
        if not isinstance(questions, list):
            msg = f"Invalid dashboard page questions for {page['page_name']}."
            raise TypeError(msg)
        for question in questions:
            lines.append(f"- {question}")
        lines.extend(["", "Visuals:"])
        for visual in page_visuals:
            lines.append(
                f"- `{visual['visual_id']}`: {visual['visual_title']} "
                f"({visual['visual_type']}) from `{visual['source_table']}`."
            )
        lines.extend(["", str(page["synthetic_data_disclaimer"]), ""])
    return lines


def _visual(
    page_name: str,
    visual_id: str,
    title: str,
    visual_type: str,
    source_table: str,
    fields: list[str],
    measures: list[str],
    filters: str,
    sort_order: str,
    conditional_formatting: str,
    business_question: str,
    caveats: str,
) -> dict[str, object]:
    return {
        "page_name": page_name,
        "visual_id": visual_id,
        "visual_title": title,
        "visual_type": visual_type,
        "source_table": source_table,
        "fields": fields,
        "measures": measures,
        "filters": filters,
        "sort_order": sort_order,
        "conditional_formatting": conditional_formatting,
        "business_question_answered": business_question,
        "caveats": caveats,
    }
