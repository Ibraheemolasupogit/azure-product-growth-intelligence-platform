"""Generate deterministic Milestone 9 experiment-analysis evidence."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from product_growth_intelligence.experiments import (
    ExperimentAnalysisConfig,
    ExperimentAnalysisResult,
    run_experiment_analysis,
)
from product_growth_intelligence.ingestion import IngestionConfig, run_batch_ingestion

EVIDENCE_DIR = Path("docs/evidence/milestone-9")
EVIDENCE_FILES = (
    "experiment-catalogue.json",
    "experiment-populations.csv",
    "assignment-integrity.csv",
    "sample-ratio-mismatch.csv",
    "metric-results.csv",
    "guardrail-results.csv",
    "segment-effects.csv",
    "multiple-testing-results.csv",
    "power-analysis.csv",
    "decision-summary.csv",
    "experiment-summary.json",
    "run-diagnostics.json",
    "analysis-manifest.json",
    "analysis-lineage.json",
    "experiment-report.md",
)


def main() -> int:
    """Run sample ingestion and experiment analysis, then copy concise evidence."""

    with TemporaryDirectory() as temp:
        root = Path(temp)
        ingestion = run_batch_ingestion(
            IngestionConfig(
                source=Path("data/samples/nexaflow"),
                output_root=root / "interim",
                quality_root=root / "quality",
                run_id="milestone9-source",
                fixed_ingestion_time="2026-01-01T00:00:00Z",
                overwrite=True,
            )
        )
        result = run_experiment_analysis(
            ExperimentAnalysisConfig(
                input_dir=ingestion.output_dir,
                output_root=root / "experiments",
                run_id="milestone9-sample",
                analysis_time="2025-06-30T23:59:59Z",
                fixed_run_time="2026-01-02T00:00:00Z",
                overwrite=True,
                evidence_mode=True,
            )
        )
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        for filename in EVIDENCE_FILES:
            shutil.copy2(result.output_dir / filename, EVIDENCE_DIR / filename)
        (EVIDENCE_DIR / "executive-experiment-report.md").write_text(
            _executive_report(result),
            encoding="utf-8",
        )
    print(f"Milestone 9 experiment evidence written to {EVIDENCE_DIR}")
    return 0


def _executive_report(result: ExperimentAnalysisResult) -> str:
    diagnostics = json.loads(
        (result.output_dir / "run-diagnostics.json").read_text(encoding="utf-8")
    )
    decisions = list(csv.DictReader((result.output_dir / "decision-summary.csv").open()))
    metrics = list(csv.DictReader((result.output_dir / "metric-results.csv").open()))
    primary = [
        row
        for row in metrics
        if row["population"] == "intention_to_treat" and row["metric_role"] == "primary"
    ]
    strongest_positive = max(
        primary,
        key=lambda row: float(
            row["estimated_effect"] if "estimated_effect" in row else row["absolute_effect"]
        ),
    )
    strongest_negative = min(primary, key=lambda row: float(row["absolute_effect"]))
    return "\n".join(
        [
            "# Executive Experiment Report",
            "",
            "Objective: evaluate synthetic NexaFlow controlled experiments with governed",
            "integrity checks, treatment effects, uncertainty, guardrails and decisions.",
            "",
            "All data is synthetic. Offline experiment analysis does not prove external",
            "validity, small samples may be underpowered, and subgroup analyses are",
            "exploratory. Decisions require product, data and risk stakeholder review.",
            "",
            f"- Experiments analysed: {result.experiments_evaluated}.",
            f"- Overall status: {result.status}.",
            f"- Valid assignments: {diagnostics['valid_assignments']}.",
            f"- SRM findings: {diagnostics['srm_findings']}.",
            f"- Guardrail failures: {diagnostics['guardrail_failures']}.",
            f"- Suppressed segment tests: {diagnostics['suppressed_segment_tests']}.",
            (
                f"- Strongest positive primary effect: {strongest_positive['experiment_id']} "
                f"({strongest_positive['absolute_effect']})."
            ),
            (
                f"- Strongest negative primary effect: {strongest_negative['experiment_id']} "
                f"({strongest_negative['absolute_effect']})."
            ),
            "",
            "Decisions:",
            *[
                f"- {row['experiment_id']}: {row['decision']} ({row['reason_codes']})."
                for row in decisions
            ],
            "",
            "Recommended next actions: increase sample sizes, investigate guardrail",
            "failures before rollout, preserve fixed-window analysis discipline, and",
            "treat segment findings as exploratory until adequately powered.",
            "",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
