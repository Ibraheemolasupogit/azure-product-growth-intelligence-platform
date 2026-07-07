"""Deterministic, evidence-grounded product insight assistant."""

from __future__ import annotations

import csv
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from product_growth_intelligence.data_generation.models import Record
from product_growth_intelligence.genai.models import ProductInsightConfig, ProductInsightResult
from product_growth_intelligence.genai.providers import provider_for
from product_growth_intelligence.ingestion.fingerprints import file_sha256, record_fingerprint
from product_growth_intelligence.metadata import get_project_metadata

ASSISTANT_VERSION = "2026-07-milestone-10"
SYNTHETIC_DISCLAIMER = "All findings are derived from synthetic NexaFlow evidence."
REQUIRED_ARTIFACTS = {
    4: ("funnel-summary.csv", "funnel-dropoff-analysis.csv", "analysis-lineage.json"),
    5: ("cohort-summary.csv", "retention-matrix.csv", "analysis-lineage.json"),
    6: ("evaluation-metrics.json", "feature-importance.csv", "model-card.md", "model-lineage.json"),
    7: ("segment-profiles.csv", "segment-card.md", "segmentation-lineage.json"),
    8: ("model-comparison.csv", "recommendation-card.md", "recommendation-lineage.json"),
    9: ("decision-summary.csv", "experiment-report.md", "analysis-lineage.json"),
}


def run_product_insights(config: ProductInsightConfig) -> ProductInsightResult:
    """Generate deterministic grounded product insights from committed evidence."""

    config.validate()
    run_id = config.run_id or _default_run_id(config)
    output_dir = config.output_root / run_id
    if output_dir.exists() and any(output_dir.iterdir()) and not config.overwrite:
        msg = f"Output directory {output_dir} already exists and is not empty. Pass --overwrite."
        raise FileExistsError(msg)
    evidence = load_evidence(config.evidence_root, config.include_milestones)
    if config.validate_only:
        return ProductInsightResult(run_id, "validated", output_dir, 0, config.provider)

    provider = provider_for(config.provider)
    inputs = build_insight_inputs(evidence)
    prompt_package = provider.build_prompt_package(inputs)
    insights = generate_grounded_insights(inputs, config.provider)
    checks = run_governance_checks(insights, evidence, prompt_package)
    diagnostics = _diagnostics(evidence, insights, checks)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_outputs(
        output_dir, config, run_id, evidence, inputs, prompt_package, insights, checks, diagnostics
    )
    return ProductInsightResult(
        run_id=run_id,
        status=str(diagnostics["overall_status"]),
        output_dir=output_dir,
        insight_count=len(insights),
        provider=config.provider,
        diagnostics=diagnostics,
    )


def load_evidence(evidence_root: Path, milestones: tuple[int, ...]) -> dict[str, Record]:
    """Load required milestone evidence artifacts."""

    loaded: dict[str, Record] = {}
    for milestone in milestones:
        milestone_dir = evidence_root / f"milestone-{milestone}"
        if not milestone_dir.exists():
            msg = f"Missing evidence directory: {milestone_dir}."
            raise FileNotFoundError(msg)
        for filename in REQUIRED_ARTIFACTS[milestone]:
            path = milestone_dir / filename
            if not path.exists():
                msg = f"Missing required evidence artifact: {path}."
                raise FileNotFoundError(msg)
            key = f"milestone_{milestone}/{filename}"
            loaded[key] = {
                "path": str(path),
                "milestone": milestone,
                "filename": filename,
                "checksum": file_sha256(path),
                "content": _read_artifact(path),
            }
    return loaded


def build_insight_inputs(evidence: dict[str, Record]) -> Record:
    """Build structured, auditable insight inputs from evidence."""

    funnel = list(_artifact(evidence, "milestone_4/funnel-summary.csv")["content"])
    retention = list(_artifact(evidence, "milestone_5/cohort-summary.csv")["content"])
    churn_metrics = dict(_artifact(evidence, "milestone_6/evaluation-metrics.json")["content"])
    feature_importance = list(_artifact(evidence, "milestone_6/feature-importance.csv")["content"])
    segments = list(_artifact(evidence, "milestone_7/segment-profiles.csv")["content"])
    recommendations = list(_artifact(evidence, "milestone_8/model-comparison.csv")["content"])
    experiments = list(_artifact(evidence, "milestone_9/decision-summary.csv")["content"])
    return {
        "funnel": _funnel_inputs(funnel),
        "retention": _retention_inputs(retention),
        "churn": _churn_inputs(churn_metrics, feature_importance),
        "segmentation": _segmentation_inputs(segments),
        "recommendations": _recommendation_inputs(recommendations),
        "experiments": _experiment_inputs(experiments),
        "evidence_inventory": [
            {
                "artifact_id": key,
                "path": value["path"],
                "checksum": value["checksum"],
                "milestone": value["milestone"],
            }
            for key, value in sorted(evidence.items())
        ],
    }


def generate_grounded_insights(inputs: Record, provider_id: str) -> list[Record]:
    """Generate deterministic insight objects from structured inputs."""

    mode = (
        "deterministic_template"
        if provider_id == "deterministic_template"
        else "azure_openai_placeholder_no_call"
    )
    insights = [
        _insight(
            "funnel",
            "funnel_health",
            "Recommendation interaction is the only observed completed funnel",
            (
                f"{inputs['funnel']['best_funnel']} reached conversion "
                f"{inputs['funnel']['best_conversion_rate']}; "
                f"{inputs['funnel']['lowest_funnel']} showed conversion "
                f"{inputs['funnel']['lowest_conversion_rate']}."
            ),
            ["milestone_4/funnel-summary.csv", "milestone_4/funnel-dropoff-analysis.csv"],
            [
                {
                    "metric_id": "overall_conversion_rate",
                    "value": inputs["funnel"]["best_conversion_rate"],
                }
            ],
            "medium",
            ["Funnel evidence is descriptive and based on synthetic sample size."],
            "Investigate onboarding and collaboration journeys with zero observed completion.",
            "Product analytics",
            "high",
            ["small_sample", "descriptive_only"],
            mode,
        ),
        _insight(
            "retention",
            "retention_pattern",
            "Most observed retention cohorts returned, with one signup cohort at zero return",
            (
                f"Median cohort return rate is {inputs['retention']['median_return_rate']}; "
                f"lowest cohort is {inputs['retention']['lowest_cohort']} at "
                f"{inputs['retention']['lowest_return_rate']}."
            ),
            ["milestone_5/cohort-summary.csv", "milestone_5/retention-matrix.csv"],
            [{"metric_id": "return_rate", "value": inputs["retention"]["lowest_return_rate"]}],
            "medium",
            ["Retention rates use observed denominators and synthetic cohorts."],
            "Review signup cohorts with low return before scaling acquisition conclusions.",
            "Growth analytics",
            "medium",
            ["small_sample"],
            mode,
        ),
        _insight(
            "churn",
            "churn_risk_driver",
            "Automation activity is the strongest churn model feature in the evidence",
            (
                f"Top churn feature is {inputs['churn']['top_feature']} with importance "
                f"{inputs['churn']['top_importance']}; test F1 is {inputs['churn']['test_f1']}."
            ),
            ["milestone_6/evaluation-metrics.json", "milestone_6/feature-importance.csv"],
            [
                {"metric_id": "feature_importance", "value": inputs["churn"]["top_importance"]},
                {"metric_id": "test_f1", "value": inputs["churn"]["test_f1"]},
            ],
            "low",
            ["Churn predictions are risk indicators, not certainties."],
            "Use churn drivers as investigation leads, not automated adverse decisions.",
            "Data science",
            "high",
            ["model_risk", "small_test_split"],
            mode,
        ),
        _insight(
            "segmentation",
            "segment_summary",
            "The largest interpretable segment is inactive or declining users",
            (
                f"{inputs['segmentation']['largest_segment_name']} covers "
                f"{inputs['segmentation']['largest_population_share']} of users in the evidence."
            ),
            ["milestone_7/segment-profiles.csv", "milestone_7/segment-card.md"],
            [
                {
                    "metric_id": "population_share",
                    "value": inputs["segmentation"]["largest_population_share"],
                }
            ],
            "medium",
            ["Segment labels are analytical interpretations, not causal identities."],
            "Prioritise re-engagement analysis for inactive or declining users.",
            "Product management",
            "high",
            ["interpretation_risk"],
            mode,
        ),
        _insight(
            "recommendation",
            "recommendation_performance",
            "Segment-aware popularity is the selected recommendation baseline",
            (
                f"Selected model {inputs['recommendations']['selected_model']} has NDCG@5 "
                f"{inputs['recommendations']['selected_ndcg']} and recall@5 "
                f"{inputs['recommendations']['selected_recall']}."
            ),
            ["milestone_8/model-comparison.csv", "milestone_8/recommendation-card.md"],
            [
                {"metric_id": "NDCG@5", "value": inputs["recommendations"]["selected_ndcg"]},
                {"metric_id": "recall@5", "value": inputs["recommendations"]["selected_recall"]},
            ],
            "medium",
            ["Recommendation scores are rankings, not probabilities."],
            "Review recommendation coverage and reasons before any user-facing use.",
            "Recommendations product",
            "medium",
            ["offline_only"],
            mode,
        ),
        _insight(
            "experiment",
            "experiment_decisions",
            "Experiment evidence blocks two treatments and leaves two without clear evidence",
            (
                f"Decision counts are {inputs['experiments']['decision_counts']}; "
                f"all sample sufficiency statuses are {inputs['experiments']['sample_statuses']}."
            ),
            ["milestone_9/decision-summary.csv", "milestone_9/experiment-report.md"],
            [{"metric_id": "decision_count", "value": inputs["experiments"]["decision_counts"]}],
            "medium",
            ["Experiment decisions include sample-size and guardrail caveats."],
            "Investigate guardrail failures and continue only adequately powered experiments.",
            "Experiment owner",
            "high",
            ["guardrail_failure", "underpowered"],
            mode,
        ),
        _insight(
            "cross_domain",
            "product_investigation_focus",
            "Activation, retention and experiment guardrails point to setup quality as a priority",
            (
                "Funnel completion gaps, churn-risk drivers and experiment guardrails all "
                "support investigating setup and reliability before scaling recommendations."
            ),
            [
                "milestone_4/funnel-summary.csv",
                "milestone_6/feature-importance.csv",
                "milestone_9/decision-summary.csv",
            ],
            [],
            "medium",
            ["Cross-domain insight combines evidence but does not prove causality."],
            "Open a product investigation on onboarding, reliability and re-engagement.",
            "Product leadership",
            "high",
            ["cross_domain_inference"],
            mode,
        ),
        _insight(
            "risk_caveat",
            "governance_caveats",
            "Synthetic evidence requires cautious interpretation",
            (
                "Reports must retain synthetic-data, offline-analysis, churn-risk, "
                "recommendation-ranking and segment-interpretation caveats."
            ),
            [
                "milestone_6/model-card.md",
                "milestone_7/segment-card.md",
                "milestone_8/recommendation-card.md",
                "milestone_9/experiment-report.md",
            ],
            [],
            "high",
            [SYNTHETIC_DISCLAIMER],
            "Keep stakeholder review before product decisions.",
            "Responsible analytics",
            "high",
            ["synthetic_data", "offline_only"],
            mode,
        ),
    ]
    return insights


def run_governance_checks(
    insights: list[Record],
    evidence: dict[str, Record],
    prompt_package: Record,
) -> Record:
    """Run deterministic insight governance checks."""

    evidence_keys = set(evidence)
    checks: Record = {
        "llm_call_performed": bool(prompt_package.get("llm_call_performed")),
        "all_insights_have_sources": all(insight["supporting_evidence"] for insight in insights),
        "all_sources_exist": all(
            source in evidence_keys
            for insight in insights
            for source in insight["supporting_evidence"]
        ),
        "synthetic_disclaimer_present": all(
            insight["synthetic_data_disclaimer"] == SYNTHETIC_DISCLAIMER for insight in insights
        ),
        "causal_language_blocked": not _contains_blocked_language(
            insights, {"caused", "guaranteed"}
        ),
        "churn_certainty_blocked": not _contains_blocked_language(
            insights, {"will churn", "certain churn"}
        ),
        "recommendation_probability_blocked": not _contains_blocked_language(
            [insight for insight in insights if insight["insight_type"] == "recommendation"],
            {"probability", "will accept"},
        ),
        "segment_interpretation_caveat_present": any(
            "analytical interpretations" in " ".join(insight["caveats"])
            for insight in insights
            if insight["insight_type"] == "segmentation"
        ),
        "experiment_caveat_present": any(
            "sample-size" in " ".join(insight["caveats"])
            for insight in insights
            if insight["insight_type"] == "experiment"
        ),
    }
    checks["overall_status"] = (
        "passed"
        if not checks["llm_call_performed"]
        and all(
            bool(value)
            for key, value in checks.items()
            if key not in {"llm_call_performed", "overall_status"}
        )
        else "failed"
    )
    return checks


def _write_outputs(
    output_dir: Path,
    config: ProductInsightConfig,
    run_id: str,
    evidence: dict[str, Record],
    inputs: Record,
    prompt_package: Record,
    insights: list[Record],
    checks: Record,
    diagnostics: Record,
) -> None:
    files: dict[str, Callable[[Path], None]] = {
        "insight-inputs.json": lambda path: _write_json(path, inputs),
        "prompt-package.json": lambda path: _write_json(path, prompt_package),
        "grounded-insights.json": lambda path: _write_json(path, insights),
        "product-health-summary.md": lambda path: _write_text(
            path, _product_health_summary(inputs, insights)
        ),
        "executive-product-insight-report.md": lambda path: _write_text(
            path, _executive_report(inputs, insights)
        ),
        "product-manager-action-brief.md": lambda path: _write_text(path, _action_brief(insights)),
        "risk-and-caveat-register.csv": lambda path: _write_csv(path, _risk_rows(insights)),
        "insight-governance-checks.json": lambda path: _write_json(path, checks),
        "assistant-lineage.json": lambda path: _write_json(path, _lineage(evidence)),
        "assistant-card.md": lambda path: _write_text(
            path, _assistant_card(config, prompt_package)
        ),
    }
    checksums = {}
    for filename, writer in files.items():
        path = output_dir / filename
        writer(path)
        checksums[filename] = file_sha256(path)
    manifest = {
        "assistant_run_id": run_id,
        "assistant_version": ASSISTANT_VERSION,
        "software_version": get_project_metadata().version,
        "provider": config.provider,
        "generation_mode": prompt_package["generation_mode"],
        "evidence_root": str(config.evidence_root),
        "included_milestones": list(config.include_milestones),
        "input_artifact_count": len(evidence),
        "insight_count": len(insights),
        "output_checksums": checksums,
        "overall_status": diagnostics["overall_status"],
        "created_at": config.fixed_run_time,
        "llm_call_performed": prompt_package["llm_call_performed"],
    }
    _write_json(output_dir / "assistant-run-manifest.json", manifest)


def _funnel_inputs(rows: list[Record]) -> Record:
    sorted_rows = sorted(rows, key=lambda row: float(row["overall_conversion_rate"]))
    best = max(rows, key=lambda row: float(row["overall_conversion_rate"]))
    lowest = sorted_rows[0]
    return {
        "best_funnel": best["funnel_id"],
        "best_conversion_rate": best["overall_conversion_rate"],
        "lowest_funnel": lowest["funnel_id"],
        "lowest_conversion_rate": lowest["overall_conversion_rate"],
        "funnel_count": len(rows),
    }


def _retention_inputs(rows: list[Record]) -> Record:
    rates = sorted(float(row["return_rate"]) for row in rows if row.get("return_rate") != "")
    lowest = min(rows, key=lambda row: float(row["return_rate"]) if row.get("return_rate") else 1.0)
    return {
        "median_return_rate": round(rates[len(rates) // 2], 6) if rates else 0.0,
        "lowest_cohort": f"{lowest['definition_id']} {lowest['cohort_period']}",
        "lowest_return_rate": lowest["return_rate"],
        "cohort_count": len(rows),
    }


def _churn_inputs(metrics: Record, feature_rows: list[Record]) -> Record:
    top = max(feature_rows, key=lambda row: float(row["importance"]))
    test = dict(metrics["test"])
    return {
        "top_feature": top["feature_name"],
        "top_importance": top["importance"],
        "test_f1": test["f1"],
        "test_row_count": test["row_count"],
    }


def _segmentation_inputs(rows: list[Record]) -> Record:
    shown = [
        row
        for row in rows
        if row["metric_name"] == "population_share" and row["suppression_status"] == "shown"
    ]
    largest = max(shown, key=lambda row: float(row["metric_value"]))
    return {
        "largest_segment_id": largest["segment_id"],
        "largest_segment_name": largest["segment_name"],
        "largest_population_share": largest["metric_value"],
    }


def _recommendation_inputs(rows: list[Record]) -> Record:
    selected = next(row for row in rows if row["selected_status"] == "selected")
    return {
        "selected_model": selected["model_id"],
        "selected_ndcg": selected["NDCG@5"],
        "selected_recall": selected["recall@5"],
        "evaluated_users": selected["evaluated_users"],
    }


def _experiment_inputs(rows: list[Record]) -> Record:
    decision_counts: dict[str, int] = {}
    for row in rows:
        decision = str(row["decision"])
        decision_counts[decision] = decision_counts.get(decision, 0) + 1
    return {
        "decision_counts": decision_counts,
        "sample_statuses": sorted({row["sample_sufficiency"] for row in rows}),
        "guardrail_failures": sum(1 for row in rows if row["guardrail_status"] == "fail"),
    }


def _insight(
    insight_type: str,
    title_slug: str,
    title: str,
    summary: str,
    evidence: list[str],
    metrics: list[Record],
    confidence: str,
    caveats: list[str],
    action: str,
    owner: str,
    priority: str,
    risk_flags: list[str],
    mode: str,
) -> Record:
    return {
        "insight_id": record_fingerprint({"type": insight_type, "title": title_slug})[:16],
        "insight_type": insight_type,
        "title": title,
        "summary": summary,
        "supporting_evidence": evidence,
        "metric_references": metrics,
        "lineage_references": [
            source.replace(".csv", "").replace(".json", "") for source in evidence
        ],
        "confidence_level": confidence,
        "caveats": caveats,
        "recommended_action": action,
        "owner_role": owner,
        "priority": priority,
        "risk_flags": risk_flags,
        "generated_by": "product_growth_intelligence.genai.deterministic_assistant",
        "generation_mode": mode,
        "synthetic_data_disclaimer": SYNTHETIC_DISCLAIMER,
    }


def _product_health_summary(inputs: Record, insights: list[Record]) -> str:
    return "\n".join(
        [
            "# Product Health Summary",
            "",
            SYNTHETIC_DISCLAIMER,
            "",
            f"Overall: {len(insights)} grounded insights were generated from committed evidence.",
            (
                "Funnel health: best observed conversion is "
                f"{inputs['funnel']['best_conversion_rate']} "
                f"for {inputs['funnel']['best_funnel']}."
            ),
            (
                "Retention health: median cohort return rate is "
                f"{inputs['retention']['median_return_rate']}."
            ),
            (
                f"Churn-risk summary: top risk driver is {inputs['churn']['top_feature']}; "
                "this is not a certainty claim."
            ),
            (
                f"Segment summary: {inputs['segmentation']['largest_segment_name']} is the "
                "largest interpreted segment."
            ),
            (
                f"Recommendation summary: selected baseline is "
                f"{inputs['recommendations']['selected_model']}."
            ),
            f"Experiment summary: decisions are {inputs['experiments']['decision_counts']}.",
            "",
            "Key caveats: synthetic data, small samples, offline-only recommendation metrics,",
            "descriptive segment labels, and experiment guardrail constraints.",
            "",
        ]
    )


def _executive_report(inputs: Record, insights: list[Record]) -> str:
    high = [insight for insight in insights if insight["priority"] == "high"]
    return "\n".join(
        [
            "# Executive Product Insight Report",
            "",
            SYNTHETIC_DISCLAIMER,
            "",
            "What is going well: retention evidence contains many returning cohorts, and",
            "recommendation analysis selected a reproducible segment-aware baseline.",
            "",
            "What needs investigation: zero-completion funnels, inactive or declining",
            "segments, churn-risk drivers, and experiment guardrail failures.",
            "",
            f"Strongest signals: {', '.join(insight['title'] for insight in high[:3])}.",
            f"Experiment decisions: {inputs['experiments']['decision_counts']}.",
            "",
            "Commercial implications: prioritise setup reliability and re-engagement",
            "investigations before scaling monetisation or recommendation changes.",
            "",
            "Governance caveats: evidence is synthetic, offline and sample-limited.",
            "Recommended next steps: assign owners to the action brief and monitor the",
            "same governed metrics in future milestones.",
            "",
        ]
    )


def _action_brief(insights: list[Record]) -> str:
    lines = [
        "# Product Manager Action Brief",
        "",
        SYNTHETIC_DISCLAIMER,
        "",
    ]
    for insight in sorted(insights, key=lambda row: str(row["priority"]), reverse=True):
        lines.extend(
            [
                f"## {insight['title']}",
                f"Evidence: {', '.join(insight['supporting_evidence'])}.",
                f"Owner: {insight['owner_role']}. Risk: {', '.join(insight['risk_flags'])}.",
                f"Action: {insight['recommended_action']}",
                f"What not to conclude: {'; '.join(insight['caveats'])}.",
                "Follow-up metrics: continue monitoring the cited governed metrics.",
                "",
            ]
        )
    return "\n".join(lines)


def _risk_rows(insights: list[Record]) -> list[Record]:
    return [
        {
            "insight_id": insight["insight_id"],
            "insight_type": insight["insight_type"],
            "title": insight["title"],
            "priority": insight["priority"],
            "risk_flags": "|".join(insight["risk_flags"]),
            "caveats": "|".join(insight["caveats"]),
            "owner_role": insight["owner_role"],
        }
        for insight in insights
    ]


def _lineage(evidence: dict[str, Record]) -> Record:
    return {
        "assistant_version": ASSISTANT_VERSION,
        "input_artifacts": [
            {
                "artifact_id": key,
                "path": value["path"],
                "checksum": value["checksum"],
                "milestone": value["milestone"],
            }
            for key, value in sorted(evidence.items())
        ],
        "relationships": [
            "committed evidence",
            "insight input contracts",
            "deterministic prompt package",
            "grounded template insights",
            "governance checks",
            "reports",
            "manifest",
        ],
    }


def _assistant_card(config: ProductInsightConfig, prompt_package: Record) -> str:
    return "\n".join(
        [
            "# Product Insight Assistant Card",
            "",
            "Intended use: deterministic local summarisation of committed synthetic",
            "analytics evidence.",
            "Out-of-scope use: live chat, automated decisions, Azure OpenAI calls,",
            "Power BI, or deployment.",
            f"Provider: {config.provider}. Generation mode: {prompt_package['generation_mode']}.",
            f"LLM call performed: {prompt_package['llm_call_performed']}.",
            "",
            "Azure mapping: evidence in ADLS Gen2 curated zones, prompt packages in Azure AI",
            "Foundry, optional future Azure OpenAI adapter, governance via Content Safety and",
            "Responsible AI controls, lineage in Microsoft Purview, secrets in Key Vault.",
            "",
            SYNTHETIC_DISCLAIMER,
            "",
        ]
    )


def _diagnostics(evidence: dict[str, Record], insights: list[Record], checks: Record) -> Record:
    return {
        "evidence_artifacts_loaded": len(evidence),
        "insights_generated": len(insights),
        "governance_status": checks["overall_status"],
        "llm_call_performed": checks["llm_call_performed"],
        "overall_status": "passed" if checks["overall_status"] == "passed" else "failed",
    }


def _artifact(evidence: dict[str, Record], key: str) -> Record:
    return evidence[key]


def _contains_blocked_language(insights: list[Record], phrases: set[str]) -> bool:
    text = " ".join(
        str(value).lower()
        for insight in insights
        for value in (insight["title"], insight["summary"], insight["recommended_action"])
    )
    return any(phrase in text for phrase in phrases)


def _read_artifact(path: Path) -> object:
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if path.suffix == ".csv":
        with path.open(encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    return path.read_text(encoding="utf-8")


def _default_run_id(config: ProductInsightConfig) -> str:
    if config.fixed_run_time:
        stamp = (
            config.fixed_run_time.replace(":", "")
            .replace("-", "")
            .replace("T", "-")
            .replace("Z", "")
        )
    else:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"product-insights-{stamp}"


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[Record]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")
