"""Generate concise deterministic Milestone 3 evidence artefacts."""

from __future__ import annotations

import shutil
from pathlib import Path

from product_growth_intelligence.ingestion import IngestionConfig, run_batch_ingestion


def main() -> int:
    """Generate evidence from the committed NexaFlow sample."""

    evidence_root = Path("docs/evidence/milestone-3")
    runtime_root = Path("/tmp/pgi-milestone-3-evidence")
    if runtime_root.exists():
        shutil.rmtree(runtime_root)
    result = run_batch_ingestion(
        IngestionConfig(
            source=Path("data/samples/nexaflow"),
            output_root=runtime_root / "interim",
            quality_root=runtime_root / "quality",
            run_id="milestone-3-sample",
            fixed_ingestion_time="2026-01-01T00:00:00Z",
            overwrite=True,
        )
    )
    if result.status == "failed":
        return 1
    evidence_root.mkdir(parents=True, exist_ok=True)
    artefacts = {
        result.quality_report_md_path: "quality-report.md",
        result.quality_report_json_path: "quality-report.json",
        result.lineage_path: "lineage.json",
        result.manifest_path: "ingestion-manifest.json",
        result.metrics_path: "run-metrics.json",
    }
    for source, target_name in artefacts.items():
        if source is None:
            return 1
        shutil.copyfile(source, evidence_root / target_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
