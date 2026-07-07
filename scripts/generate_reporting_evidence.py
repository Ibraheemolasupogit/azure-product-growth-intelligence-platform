"""Generate deterministic Milestone 11 reporting evidence."""

from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from product_growth_intelligence.reporting import (
    ReportingLayerConfig,
    ReportingLayerResult,
    run_reporting_layer,
)

EVIDENCE_DIR = Path("docs/evidence/milestone-11")
EVIDENCE_FILES = (
    "reporting-manifest.json",
    "reporting-lineage.json",
    "reporting-diagnostics.json",
    "semantic-model.json",
    "semantic-model.md",
    "metric-dictionary.csv",
    "dashboard-specification.md",
    "dashboard-pages.json",
    "visual-specifications.json",
    "powerbi-refresh-plan.md",
    "powerbi-governance-notes.md",
    "executive-reporting-summary.md",
    "fact_product_health.csv",
    "fact_funnel_performance.csv",
    "fact_retention.csv",
    "fact_churn_model_performance.csv",
    "fact_segment_profiles.csv",
    "fact_recommendation_performance.csv",
    "fact_experiment_decisions.csv",
    "fact_product_insights.csv",
    "dim_metric.csv",
    "dim_milestone.csv",
    "dim_analysis_domain.csv",
    "dim_date.csv",
)


def main() -> int:
    """Generate concise deterministic reporting evidence."""

    with TemporaryDirectory() as temp:
        result = run_reporting_layer(
            ReportingLayerConfig(
                evidence_root=Path("docs/evidence"),
                output_root=Path(temp) / "reporting",
                run_id="milestone11-sample",
                fixed_run_time="2026-01-02T00:00:00Z",
                overwrite=True,
                evidence_mode=True,
            )
        )
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        for filename in EVIDENCE_FILES:
            shutil.copy2(result.output_dir / filename, EVIDENCE_DIR / filename)
    print(f"Milestone 11 reporting evidence written to {EVIDENCE_DIR}")
    return 0


def run_sample() -> ReportingLayerResult:
    """Run the evidence path for tests."""

    with TemporaryDirectory() as temp:
        return run_reporting_layer(
            ReportingLayerConfig(
                evidence_root=Path("docs/evidence"),
                output_root=Path(temp) / "reporting",
                run_id="milestone11-sample",
                fixed_run_time="2026-01-02T00:00:00Z",
                overwrite=True,
            )
        )


if __name__ == "__main__":
    raise SystemExit(main())
