"""Generate deterministic Milestone 10 product insight evidence."""

from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from product_growth_intelligence.genai import (
    ProductInsightConfig,
    ProductInsightResult,
    run_product_insights,
)

EVIDENCE_DIR = Path("docs/evidence/milestone-10")
EVIDENCE_FILES = (
    "grounded-insights.json",
    "product-health-summary.md",
    "executive-product-insight-report.md",
    "product-manager-action-brief.md",
    "risk-and-caveat-register.csv",
    "insight-governance-checks.json",
    "assistant-run-manifest.json",
    "assistant-lineage.json",
    "assistant-card.md",
)


def main() -> int:
    """Generate concise deterministic product insight evidence."""

    with TemporaryDirectory() as temp:
        result = run_product_insights(
            ProductInsightConfig(
                evidence_root=Path("docs/evidence"),
                output_root=Path(temp) / "product-insights",
                run_id="milestone10-sample",
                provider="deterministic_template",
                fixed_run_time="2026-01-02T00:00:00Z",
                overwrite=True,
                evidence_mode=True,
            )
        )
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        for filename in EVIDENCE_FILES:
            shutil.copy2(result.output_dir / filename, EVIDENCE_DIR / filename)
    print(f"Milestone 10 product insight evidence written to {EVIDENCE_DIR}")
    return 0


def run_sample() -> ProductInsightResult:
    """Run the evidence path for tests."""

    with TemporaryDirectory() as temp:
        return run_product_insights(
            ProductInsightConfig(
                evidence_root=Path("docs/evidence"),
                output_root=Path(temp) / "product-insights",
                run_id="milestone10-sample",
                provider="deterministic_template",
                fixed_run_time="2026-01-02T00:00:00Z",
                overwrite=True,
            )
        )


if __name__ == "__main__":
    raise SystemExit(main())
