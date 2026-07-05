"""Generate deterministic Milestone 8 recommendation evidence."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from product_growth_intelligence.ingestion import IngestionConfig, run_batch_ingestion
from product_growth_intelligence.models.recommendations import (
    RecommendationConfig,
    RecommendationResult,
    run_recommendations,
)

EVIDENCE_DIR = Path("docs/evidence/milestone-8")
EVIDENCE_FILES = (
    "recommendation-definition.json",
    "item-catalogue.json",
    "interaction-mapping.json",
    "model-comparison.csv",
    "offline-metrics.json",
    "metrics-by-k.csv",
    "segment-metrics.csv",
    "cold-start-metrics.json",
    "item-similarity.csv",
    "catalogue-coverage.csv",
    "model-metadata.json",
    "run-diagnostics.json",
    "recommendation-manifest.json",
    "recommendation-lineage.json",
    "recommendation-card.md",
)


def main() -> int:
    """Run sample ingestion and recommendations, then copy concise evidence."""

    with TemporaryDirectory() as temp:
        root = Path(temp)
        ingestion = run_batch_ingestion(
            IngestionConfig(
                source=Path("data/samples/nexaflow"),
                output_root=root / "interim",
                quality_root=root / "quality",
                run_id="milestone8-source",
                fixed_ingestion_time="2026-01-01T00:00:00Z",
                overwrite=True,
            )
        )
        result = run_recommendations(
            RecommendationConfig(
                input_dir=ingestion.output_dir,
                output_root=root / "models" / "recommendations",
                run_id="milestone8-sample",
                snapshot_time="2025-02-28T23:59:59Z",
                lookback_days=56,
                holdout_days=28,
                fixed_run_time="2026-01-02T00:00:00Z",
                overwrite=True,
                evidence_mode=True,
            )
        )
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        for filename in EVIDENCE_FILES:
            shutil.copy2(result.output_dir / filename, EVIDENCE_DIR / filename)
        (EVIDENCE_DIR / "executive-recommendation-report.md").write_text(
            _executive_report(result),
            encoding="utf-8",
        )
    print(f"Milestone 8 recommendation evidence written to {EVIDENCE_DIR}")
    return 0


def _executive_report(result: RecommendationResult) -> str:
    metadata = json.loads((result.output_dir / "model-metadata.json").read_text(encoding="utf-8"))
    diagnostics = json.loads(
        (result.output_dir / "run-diagnostics.json").read_text(encoding="utf-8")
    )
    comparison = list(csv.DictReader((result.output_dir / "model-comparison.csv").open()))
    selected = next(row for row in comparison if row["selected_status"] == "selected")
    return "\n".join(
        [
            "# Executive Recommendation Report",
            "",
            "Objective: provide a deterministic, interpretable recommendation baseline for",
            "synthetic NexaFlow product actions and resources.",
            "",
            "All data is synthetic. The outputs are offline portfolio evidence only; they are",
            "not an online recommender, experiment winner, treatment policy, or causal model.",
            "",
            f"- Recommendation run: {result.run_id}.",
            f"- Selected model: {result.selected_model}.",
            f"- Eligible users: {result.eligible_users}.",
            f"- Evaluated users with holdout activity: {result.evaluated_users}.",
            f"- Catalogue size: {metadata['catalogue_size']}.",
            f"- Interaction rows: {metadata['interaction_count']}.",
            f"- Candidate rows: {metadata['candidate_count']}.",
            f"- Selected NDCG@5: {selected['NDCG@5']}.",
            f"- Selected recall@5: {selected['recall@5']}.",
            f"- Fallback recommendations: {diagnostics['fallback_counts']}.",
            "",
            "Recommended next steps: inspect segment-level coverage, review sparse items,",
            "validate catalogue eligibility with product stakeholders, and require online",
            "experimentation before any production serving or user-facing optimisation.",
            "",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
