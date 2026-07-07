"""Build compact Power BI-ready reporting tables."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from product_growth_intelligence.reporting.evidence_loader import (
    EvidenceArtifact,
    artifact_json,
    artifact_list,
    artifact_rows,
)
from product_growth_intelligence.reporting.writers import normalise_number

ReportingTables = dict[str, list[dict[str, object]]]


def build_reporting_tables(evidence: dict[str, EvidenceArtifact]) -> ReportingTables:
    """Create star-schema style fact and dimension tables."""

    tables: ReportingTables = {
        "fact_product_health": _fact_product_health(evidence),
        "fact_funnel_performance": _fact_funnel_performance(evidence),
        "fact_retention": _fact_retention(evidence),
        "fact_churn_model_performance": _fact_churn(evidence),
        "fact_segment_profiles": _fact_segments(evidence),
        "fact_recommendation_performance": _fact_recommendations(evidence),
        "fact_experiment_decisions": _fact_experiments(evidence),
        "fact_product_insights": _fact_product_insights(evidence),
        "dim_metric": _dim_metric(),
        "dim_milestone": _dim_milestone(),
        "dim_analysis_domain": _dim_analysis_domain(),
        "dim_date": _dim_date(),
    }
    return tables


def _fact_product_health(evidence: dict[str, EvidenceArtifact]) -> list[dict[str, object]]:
    funnel = artifact_rows(evidence, "milestone_4/funnel-summary.csv")
    retention = artifact_rows(evidence, "milestone_5/cohort-summary.csv")
    churn = artifact_json(evidence, "milestone_6/evaluation-metrics.json")["test"]
    recommendations = artifact_rows(evidence, "milestone_8/model-comparison.csv")
    experiments = artifact_rows(evidence, "milestone_9/decision-summary.csv")
    insights = artifact_rows(evidence, "milestone_10/risk-and-caveat-register.csv")
    selected = next(
        (row for row in recommendations if row.get("selected_status") == "selected"),
        None,
    )
    if selected is None:
        msg = "Recommendation evidence does not contain a selected model."
        raise ValueError(msg)
    completed = sum(int(row["completed"]) for row in funnel)
    entrants = sum(int(row["entrants"]) for row in funnel)
    avg_return = _average(row["return_rate"] for row in retention)
    decision_counts = Counter(row["decision"] for row in experiments)
    return [
        _row(
            "product_health",
            "portfolio_product_health",
            "Executive Product Health",
            "milestone_10/grounded-insights.json",
            product_health_score=round(
                (_safe_rate(completed, entrants) + avg_return + float(selected["NDCG@5"])) / 3,
                6,
            ),
            funnel_completion_rate=_safe_rate(completed, entrants),
            average_cohort_return_rate=avg_return,
            churn_test_f1=normalise_number(churn["f1"]),
            recommendation_ndcg_at_5=normalise_number(selected["NDCG@5"]),
            blocked_experiments=decision_counts["do_not_ship"],
            generated_insights=len(insights),
        )
    ]


def _fact_funnel_performance(evidence: dict[str, EvidenceArtifact]) -> list[dict[str, object]]:
    return [
        _row(
            "funnel",
            row["funnel_id"],
            row["funnel_id"].replace("_", " ").title(),
            "milestone_4/funnel-summary.csv",
            eligible_users=normalise_number(row["eligible_users"]),
            entrants=normalise_number(row["entrants"]),
            completed=normalise_number(row["completed"]),
            abandoned=normalise_number(row["abandoned"]),
            entry_rate=normalise_number(row["entry_rate"]),
            overall_conversion_rate=normalise_number(row["overall_conversion_rate"]),
            fully_observed_conversion_rate=normalise_number(row["fully_observed_conversion_rate"]),
            status=row["status"],
        )
        for row in artifact_rows(evidence, "milestone_4/funnel-summary.csv")
    ]


def _fact_retention(evidence: dict[str, EvidenceArtifact]) -> list[dict[str, object]]:
    return [
        _row(
            "retention",
            f"{row['definition_id']}:{row['cohort_period']}",
            f"{row['definition_id']} {row['cohort_period']}",
            "milestone_5/cohort-summary.csv",
            definition_id=row["definition_id"],
            cohort_period=row["cohort_period"],
            cohort_size=normalise_number(row["cohort_size"]),
            users_returning_after_period_0=normalise_number(row["users_returning_after_period_0"]),
            return_rate=normalise_number(row["return_rate"]),
            inactive_users=normalise_number(row["inactive_users"]),
            resurrected_users=normalise_number(row["resurrected_users"]),
            status=row["status"],
        )
        for row in artifact_rows(evidence, "milestone_5/cohort-summary.csv")[:24]
    ]


def _fact_churn(evidence: dict[str, EvidenceArtifact]) -> list[dict[str, object]]:
    metrics = artifact_json(evidence, "milestone_6/evaluation-metrics.json")
    rows = []
    for split in ("validation", "test"):
        values = metrics[split]
        rows.append(
            _row(
                "churn",
                f"churn_{split}",
                f"Churn {split.title()} Performance",
                "milestone_6/evaluation-metrics.json",
                split=split,
                accuracy=normalise_number(values["accuracy"]),
                precision=normalise_number(values["precision"]),
                recall=normalise_number(values["recall"]),
                f1=normalise_number(values["f1"]),
                roc_auc=normalise_number(values["roc_auc"]),
                average_precision=normalise_number(values["average_precision"]),
                brier_score=normalise_number(values["brier_score"]),
            )
        )
    return rows


def _fact_segments(evidence: dict[str, EvidenceArtifact]) -> list[dict[str, object]]:
    profiles = artifact_rows(evidence, "milestone_7/segment-profiles.csv")
    rows = []
    seen: set[str] = set()
    for profile in profiles:
        segment_id = profile["segment_id"]
        if segment_id in seen:
            continue
        seen.add(segment_id)
        rows.append(
            _row(
                "segmentation",
                segment_id,
                profile["segment_name"],
                "milestone_7/segment-profiles.csv",
                method=profile["method"],
                user_count=normalise_number(profile["user_count"]),
                population_share=normalise_number(profile["population_share"]),
                suppression_status=profile["suppression_status"],
            )
        )
    return rows


def _fact_recommendations(evidence: dict[str, EvidenceArtifact]) -> list[dict[str, object]]:
    return [
        _row(
            "recommendations",
            row["model_id"],
            row["algorithm"],
            "milestone_8/model-comparison.csv",
            selected_status=row["selected_status"],
            evaluated_users=normalise_number(row["evaluated_users"]),
            precision_at_5=normalise_number(row["precision@5"]),
            recall_at_5=normalise_number(row["recall@5"]),
            ndcg_at_5=normalise_number(row["NDCG@5"]),
            catalogue_coverage_at_5=normalise_number(row["catalogue_coverage@5"]),
            novelty_at_5=normalise_number(row["novelty@5"]),
            diversity_at_5=normalise_number(row["diversity@5"]),
            fallback_rate=normalise_number(row["fallback_rate"]),
        )
        for row in artifact_rows(evidence, "milestone_8/model-comparison.csv")
    ]


def _fact_experiments(evidence: dict[str, EvidenceArtifact]) -> list[dict[str, object]]:
    return [
        _row(
            "experiments",
            row["experiment_id"],
            row["experiment_id"].replace("_", " ").title(),
            "milestone_9/decision-summary.csv",
            treatment_variant=row["treatment_variant"],
            primary_metric=row["primary_metric"],
            decision=row["decision"],
            estimated_effect=normalise_number(row["estimated_effect"]),
            p_value=normalise_number(row["p_value"]),
            adjusted_p_value=normalise_number(row["adjusted_p_value"]),
            guardrail_status=row["guardrail_status"],
            sample_sufficiency=row["sample_sufficiency"],
            reason_codes=row["reason_codes"],
        )
        for row in artifact_rows(evidence, "milestone_9/decision-summary.csv")
    ]


def _fact_product_insights(evidence: dict[str, EvidenceArtifact]) -> list[dict[str, object]]:
    insights = artifact_list(evidence, "milestone_10/grounded-insights.json")
    return [
        _row(
            "product_insights",
            str(insight["insight_id"]),
            str(insight["title"]),
            "milestone_10/grounded-insights.json",
            insight_type=insight["insight_type"],
            priority=insight["priority"],
            confidence=insight["confidence_level"],
            owner_role=insight["owner_role"],
            source_count=len(insight["lineage_references"]),
            caveat_count=len(insight["caveats"]),
        )
        for insight in insights
    ]


def _dim_metric() -> list[dict[str, object]]:
    return [
        {"metric_id": metric_id, "metric_name": name, "domain": domain, "sort_order": index}
        for index, (metric_id, name, domain) in enumerate(
            [
                ("funnel_conversion_rate", "Funnel Conversion Rate", "funnel"),
                ("stage_dropoff_rate", "Stage Drop-off Rate", "funnel"),
                ("classic_retention_rate", "Classic Retention Rate", "retention"),
                ("rolling_retention_rate", "Rolling Retention Rate", "retention"),
                ("churn_precision", "Churn Precision", "churn"),
                ("churn_recall", "Churn Recall", "churn"),
                ("segment_population_share", "Segment Population Share", "segmentation"),
                ("recommendation_ndcg_at_5", "Recommendation NDCG@5", "recommendations"),
                ("experiment_treatment_effect", "Experiment Treatment Effect", "experiments"),
                ("guardrail_failure_count", "Guardrail Failure Count", "experiments"),
                (
                    "insight_governance_pass_rate",
                    "Insight Governance Pass Rate",
                    "product_insights",
                ),
                ("data_quality_status", "Data Quality Status", "governance"),
            ],
            start=1,
        )
    ]


def _dim_milestone() -> list[dict[str, object]]:
    return [
        {
            "milestone_key": f"milestone_{number}",
            "milestone_number": number,
            "display_name": name,
            "status": "completed",
            "synthetic_data_flag": True,
        }
        for number, name in [
            (4, "Funnel Analytics"),
            (5, "Retention and Cohorts"),
            (6, "Churn Prediction"),
            (7, "User Segmentation"),
            (8, "Recommendation Baselines"),
            (9, "Experiment Analysis"),
            (10, "Product Insight Assistant"),
            (11, "Power BI-ready Reporting Layer"),
        ]
    ]


def _dim_analysis_domain() -> list[dict[str, object]]:
    domains = [
        ("product_health", "Product Health"),
        ("funnel", "Funnel and Activation"),
        ("retention", "Retention and Cohorts"),
        ("churn", "Churn Risk"),
        ("segmentation", "Segmentation"),
        ("recommendations", "Recommendations"),
        ("experiments", "Experiments"),
        ("product_insights", "Product Insights"),
        ("governance", "Governance and Lineage"),
    ]
    return [
        {"domain_key": key, "display_name": name, "sort_order": index, "synthetic_data_flag": True}
        for index, (key, name) in enumerate(domains, start=1)
    ]


def _dim_date() -> list[dict[str, object]]:
    return [
        {
            "date_key": "2026-01-02",
            "date": "2026-01-02",
            "year": 2026,
            "month": 1,
            "day": 2,
            "label": "Fixed deterministic reporting run date",
        }
    ]


def _row(
    domain: str,
    stable_id: str,
    name: str,
    source_artifact: str,
    **values: object,
) -> dict[str, object]:
    return {
        "domain_key": domain,
        "stable_id": stable_id,
        "display_name": name,
        "source_artifact": source_artifact,
        "lineage_reference": source_artifact,
        "synthetic_data_flag": True,
        **values,
    }


def _average(values: Iterable[str]) -> float:
    numbers = [float(value) for value in values if value != ""]
    if not numbers:
        return 0.0
    return round(sum(numbers) / len(numbers), 6)


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 6)
