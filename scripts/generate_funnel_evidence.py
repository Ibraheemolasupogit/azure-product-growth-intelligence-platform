"""Generate deterministic Milestone 4 funnel evidence."""

from __future__ import annotations

import shutil
from pathlib import Path

from product_growth_intelligence.analytics import FunnelAnalysisConfig, run_funnel_analysis
from product_growth_intelligence.ingestion import IngestionConfig, run_batch_ingestion


def main() -> int:
    """Regenerate concise committed funnel evidence."""

    runtime_root = Path("/tmp/pgi-milestone-4-evidence")
    evidence_root = Path("docs/evidence/milestone-4")
    if runtime_root.exists():
        shutil.rmtree(runtime_root)
    ingestion = run_batch_ingestion(
        IngestionConfig(
            source=Path("data/samples/nexaflow"),
            output_root=runtime_root / "interim",
            quality_root=runtime_root / "quality",
            run_id="milestone4-source",
            fixed_ingestion_time="2026-01-01T00:00:00Z",
            overwrite=True,
        )
    )
    if ingestion.status == "failed":
        return 1
    analysis = run_funnel_analysis(
        FunnelAnalysisConfig(
            input_dir=runtime_root / "interim" / "milestone4-source",
            output_root=runtime_root / "funnels",
            run_id="milestone-4-sample",
            fixed_analysis_time="2026-01-02T00:00:00Z",
            suppression_threshold=1,
            overwrite=True,
            evidence_mode=True,
        )
    )
    if analysis.status == "failed":
        return 1
    evidence_root.mkdir(parents=True, exist_ok=True)
    for filename in (
        "funnel-summary.csv",
        "funnel-stage-metrics.csv",
        "funnel-dropoff-analysis.csv",
        "funnel-diagnostics.json",
        "analysis-manifest.json",
        "analysis-lineage.json",
        "executive-funnel-report.md",
    ):
        shutil.copyfile(analysis.output_dir / filename, evidence_root / filename)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
