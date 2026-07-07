"""Typed configuration for the reporting layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ReportingLayerConfig:
    """Configuration for building deterministic Power BI-ready reporting outputs."""

    evidence_root: Path = Path("docs/evidence")
    output_root: Path = Path("outputs/reporting/powerbi")
    run_id: str | None = None
    include_domains: tuple[str, ...] = field(default_factory=tuple)
    fixed_run_time: str | None = None
    overwrite: bool = False
    validate_only: bool = False
    evidence_mode: bool = False

    def validate(self) -> None:
        """Validate user supplied options."""

        unsupported = set(self.include_domains) - SUPPORTED_DOMAINS
        if unsupported:
            msg = f"Unsupported reporting domain(s): {', '.join(sorted(unsupported))}."
            raise ValueError(msg)


@dataclass(frozen=True)
class ReportingLayerResult:
    """Summary returned by a reporting-layer run."""

    run_id: str
    status: str
    output_dir: Path
    table_count: int
    metric_count: int
    visual_count: int
    diagnostics: dict[str, object]


SUPPORTED_DOMAINS = {
    "product_health",
    "funnel",
    "retention",
    "churn",
    "segmentation",
    "recommendations",
    "experiments",
    "product_insights",
    "governance",
}
