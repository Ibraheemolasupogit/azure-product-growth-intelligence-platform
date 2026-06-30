"""Generate deterministic Milestone 5 retention evidence."""

from __future__ import annotations

import shutil
from pathlib import Path

from product_growth_intelligence.analytics.retention import (
    RetentionAnalysisConfig,
    run_retention_analysis,
)
from product_growth_intelligence.ingestion import IngestionConfig, run_batch_ingestion


def main() -> int:
    """Regenerate concise committed retention evidence."""

    runtime_root = Path("/tmp/pgi-milestone-5-evidence")
    evidence_root = Path("docs/evidence/milestone-5")
    if runtime_root.exists():
        shutil.rmtree(runtime_root)
    ingestion = run_batch_ingestion(
        IngestionConfig(
            source=Path("data/samples/nexaflow"),
            output_root=runtime_root / "interim",
            quality_root=runtime_root / "quality",
            run_id="milestone5-source",
            fixed_ingestion_time="2026-01-01T00:00:00Z",
            overwrite=True,
        )
    )
    if ingestion.status == "failed":
        return 1
    analysis = run_retention_analysis(
        RetentionAnalysisConfig(
            input_dir=runtime_root / "interim" / "milestone5-source",
            output_root=runtime_root / "retention",
            run_id="milestone-5-sample",
            time_grain="weekly",
            horizon=8,
            suppression_threshold=1,
            fixed_analysis_time="2026-01-02T00:00:00Z",
            overwrite=True,
            evidence_mode=True,
        )
    )
    if analysis.status == "failed":
        return 1
    evidence_root.mkdir(parents=True, exist_ok=True)
    for filename in (
        "retention-matrix.csv",
        "retention-long.csv",
        "cohort-summary.csv",
        "segment-retention.csv",
        "resurrection-analysis.csv",
        "retention-diagnostics.json",
        "analysis-manifest.json",
        "analysis-lineage.json",
        "executive-retention-report.md",
    ):
        shutil.copyfile(analysis.output_dir / filename, evidence_root / filename)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
