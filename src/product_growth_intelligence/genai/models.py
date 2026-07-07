"""Typed models for deterministic product insight generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

InsightProvider = Literal["deterministic_template", "azure_openai_placeholder"]


@dataclass(frozen=True)
class ProductInsightConfig:
    """Configuration for one product insight assistant run."""

    evidence_root: Path
    output_root: Path
    run_id: str | None = None
    provider: InsightProvider = "deterministic_template"
    include_milestones: tuple[int, ...] = (4, 5, 6, 7, 8, 9)
    fixed_run_time: str | None = None
    overwrite: bool = False
    validate_only: bool = False
    evidence_mode: bool = False

    def validate(self) -> None:
        """Validate configuration values."""

        if self.provider not in {"deterministic_template", "azure_openai_placeholder"}:
            msg = "Unsupported insight provider."
            raise ValueError(msg)
        if not self.include_milestones:
            msg = "At least one milestone must be included."
            raise ValueError(msg)
        supported = {4, 5, 6, 7, 8, 9}
        unknown = sorted(set(self.include_milestones) - supported)
        if unknown:
            msg = f"Unsupported evidence milestones: {unknown}."
            raise ValueError(msg)


@dataclass(frozen=True)
class ProductInsightResult:
    """Completed product insight run summary."""

    run_id: str
    status: str
    output_dir: Path
    insight_count: int
    provider: str
    diagnostics: dict[str, object] = field(default_factory=dict)
