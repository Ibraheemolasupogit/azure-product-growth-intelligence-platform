"""Generate deterministic Milestone 6 churn model evidence."""

from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from product_growth_intelligence.ingestion import IngestionConfig, run_batch_ingestion
from product_growth_intelligence.models.churn import (
    ChurnTrainingConfig,
    ChurnTrainingResult,
    run_churn_training,
)

EVIDENCE_DIR = Path("docs/evidence/milestone-6")
EVIDENCE_FILES = (
    "churn-definition.json",
    "feature-catalogue.json",
    "dataset-splits.csv",
    "evaluation-metrics.json",
    "threshold-analysis.csv",
    "feature-importance.csv",
    "model-metadata.json",
    "model-card.md",
    "run-diagnostics.json",
    "model-manifest.json",
    "model-lineage.json",
)


def main() -> int:
    """Run ingestion and churn training, then copy evidence artifacts."""

    with TemporaryDirectory() as temp:
        root = Path(temp)
        ingestion = run_batch_ingestion(
            IngestionConfig(
                source=Path("data/samples/nexaflow"),
                output_root=root / "interim",
                quality_root=root / "quality",
                run_id="milestone6-source",
                fixed_ingestion_time="2026-01-01T00:00:00Z",
                overwrite=True,
            )
        )
        result = run_churn_training(
            ChurnTrainingConfig(
                input_dir=ingestion.output_dir,
                output_root=root / "models" / "churn",
                run_id="milestone6-sample",
                analysis_end="2025-03-31T23:59:59Z",
                fixed_run_time="2026-01-02T00:00:00Z",
                model="logistic",
                overwrite=True,
            )
        )
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        for filename in EVIDENCE_FILES:
            shutil.copy2(result.output_dir / filename, EVIDENCE_DIR / filename)
        (EVIDENCE_DIR / "executive-churn-report.md").write_text(
            _executive_report(result),
            encoding="utf-8",
        )
    print(f"Milestone 6 churn evidence written to {EVIDENCE_DIR}")
    return 0


def _executive_report(result: ChurnTrainingResult) -> str:
    return "\n".join(
        [
            "# Executive Churn Report",
            "",
            "Scope: deterministic churn modelling over trusted synthetic Milestone 3 sample data.",
            "",
            "All data is synthetic. This model is a demonstration, predictions are probabilistic,",
            "feature importance is associative rather than causal, and the model must not be used",
            "for automated adverse decisions.",
            "",
            f"- Snapshot rows: {result.row_count}.",
            f"- Behavioural churn prevalence: {result.label_prevalence}.",
            f"- Selected model: {result.selected_model}.",
            f"- Selected threshold: {result.selected_threshold}.",
            "",
            "Recommended next investigations: validate on larger non-synthetic data,",
            "monitor drift,",
            "review subgroup coverage, and test retention interventions with governed experiments.",
            "",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
