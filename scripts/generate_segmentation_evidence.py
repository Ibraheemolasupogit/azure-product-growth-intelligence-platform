"""Generate deterministic Milestone 7 segmentation evidence."""

from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from product_growth_intelligence.ingestion import IngestionConfig, run_batch_ingestion
from product_growth_intelligence.models.segmentation import SegmentationConfig, run_segmentation
from product_growth_intelligence.models.segmentation.models import SegmentationResult

EVIDENCE_DIR = Path("docs/evidence/milestone-7")
EVIDENCE_FILES = (
    "segmentation-definition.json",
    "cluster-candidate-metrics.csv",
    "cluster-stability.csv",
    "segment-profiles.csv",
    "cluster-centroids.csv",
    "pca-explained-variance.csv",
    "segment-name-mapping.json",
    "model-metadata.json",
    "run-diagnostics.json",
    "segmentation-manifest.json",
    "segmentation-lineage.json",
    "segment-card.md",
)


def main() -> int:
    """Run sample ingestion and segmentation, then copy concise evidence."""

    with TemporaryDirectory() as temp:
        root = Path(temp)
        ingestion = run_batch_ingestion(
            IngestionConfig(
                source=Path("data/samples/nexaflow"),
                output_root=root / "interim",
                quality_root=root / "quality",
                run_id="milestone7-source",
                fixed_ingestion_time="2026-01-01T00:00:00Z",
                overwrite=True,
            )
        )
        result = run_segmentation(
            SegmentationConfig(
                input_dir=ingestion.output_dir,
                output_root=root / "models" / "segmentation",
                run_id="milestone7-sample",
                snapshot_time="2025-03-31T23:59:59Z",
                lookback_days=56,
                fixed_run_time="2026-01-02T00:00:00Z",
                overwrite=True,
                evidence_mode=True,
            )
        )
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        for filename in EVIDENCE_FILES:
            shutil.copy2(result.output_dir / filename, EVIDENCE_DIR / filename)
        (EVIDENCE_DIR / "executive-segmentation-report.md").write_text(
            _executive_report(result),
            encoding="utf-8",
        )
    print(f"Milestone 7 segmentation evidence written to {EVIDENCE_DIR}")
    return 0


def _executive_report(result: SegmentationResult) -> str:
    return "\n".join(
        [
            "# Executive Segmentation Report",
            "",
            "Objective: describe deterministic behavioural user groups for product analysis.",
            "",
            "All data is synthetic. Segment names are analytical interpretations, clusters do",
            "not prove causal behaviour, and small-sample evidence is illustrative. Segments",
            "should be reviewed by domain experts before operational use.",
            "",
            f"- Eligible snapshots: {result.eligible_snapshots}.",
            f"- Selected algorithm: {result.selected_algorithm}.",
            f"- Selected cluster count: {result.selected_cluster_count}.",
            "",
            "Recommended investigations: compare segment adoption patterns, review onboarding",
            "needs for inactive or exploratory users, inspect high-friction users, and validate",
            "the segmentation on larger non-synthetic samples.",
            "",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
