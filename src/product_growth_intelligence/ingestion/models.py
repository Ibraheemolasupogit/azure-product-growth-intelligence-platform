"""Typed ingestion models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from product_growth_intelligence.data_generation.models import JsonValue, Record
from product_growth_intelligence.validation.rule_models import RuleResult, SourceLocation
from product_growth_intelligence.validation.schema_drift import SchemaDriftFinding, SchemaPolicy

DuplicatePolicy = Literal["reject", "keep-first", "keep-last"]
IngestionMode = Literal["batch", "stream"]


@dataclass(frozen=True)
class IngestionConfig:
    """Configuration for local ingestion runs."""

    source: Path
    output_root: Path
    quality_root: Path
    run_id: str | None = None
    mode: IngestionMode = "batch"
    contract_version: str = "2026-06-milestone-3"
    schema_policy: SchemaPolicy = "strict"
    duplicate_policy: DuplicatePolicy = "reject"
    checksum_enforcement: bool = True
    max_quarantine_rate: float = 0.0
    max_critical_failures: int = 0
    fixed_ingestion_time: str | None = None
    overwrite: bool = False
    validate_only: bool = False
    stream_micro_batch_size: int = 25

    def validate(self) -> None:
        """Validate configuration values."""

        if self.schema_policy not in {"strict", "compatible", "report-only"}:
            msg = f"Unsupported schema policy: {self.schema_policy}."
            raise ValueError(msg)
        if self.duplicate_policy not in {"reject", "keep-first", "keep-last"}:
            msg = f"Unsupported duplicate policy: {self.duplicate_policy}."
            raise ValueError(msg)
        if not 0 <= self.max_quarantine_rate <= 1:
            msg = "max_quarantine_rate must be between 0 and 1."
            raise ValueError(msg)
        if self.max_critical_failures < 0:
            msg = "max_critical_failures cannot be negative."
            raise ValueError(msg)
        if self.stream_micro_batch_size < 1:
            msg = "stream_micro_batch_size must be greater than zero."
            raise ValueError(msg)


@dataclass(frozen=True)
class ParsedRecord:
    """A source record after parsing and type normalisation."""

    dataset: str
    source_file: str
    source_location: SourceLocation
    raw_record: JsonValue
    record: Record | None
    parse_errors: tuple[RuleResult, ...] = ()


@dataclass(frozen=True)
class IngestionMetadata:
    """Metadata attached to accepted and quarantined records."""

    ingestion_run_id: str
    source_dataset: str
    source_file: str
    source_row_number: int | None
    source_line_number: int | None
    source_generation_run_id: str | None
    ingested_at: str
    contract_version: str
    record_status: str
    quality_rule_ids: tuple[str, ...]
    record_fingerprint: str | None

    def to_dict(self) -> dict[str, JsonValue]:
        """Return JSON-ready metadata."""

        return {
            "ingestion_run_id": self.ingestion_run_id,
            "source_dataset": self.source_dataset,
            "source_file": self.source_file,
            "source_row_number": self.source_row_number,
            "source_line_number": self.source_line_number,
            "source_generation_run_id": self.source_generation_run_id,
            "ingested_at": self.ingested_at,
            "contract_version": self.contract_version,
            "record_status": self.record_status,
            "quality_rule_ids": list(self.quality_rule_ids),
            "record_fingerprint": self.record_fingerprint,
        }


@dataclass
class DatasetIngestionResult:
    """Accepted and quarantined records for one dataset."""

    dataset: str
    accepted: list[Record] = field(default_factory=list)
    quarantined: list[Record] = field(default_factory=list)
    rules: list[RuleResult] = field(default_factory=list)
    schema_drift: list[SchemaDriftFinding] = field(default_factory=list)
    source_count: int = 0
    accepted_count: int = 0
    quarantined_count: int = 0


@dataclass(frozen=True)
class PipelineResult:
    """Top-level ingestion pipeline result."""

    run_id: str
    status: Literal["passed", "passed_with_warnings", "failed"]
    output_dir: Path
    quality_dir: Path
    dataset_results: dict[str, DatasetIngestionResult]
    manifest_path: Path | None
    quality_report_json_path: Path | None
    quality_report_md_path: Path | None
    lineage_path: Path | None
    metrics_path: Path | None

    @property
    def accepted_count(self) -> int:
        """Return total accepted records."""

        return sum(result.accepted_count for result in self.dataset_results.values())

    @property
    def quarantined_count(self) -> int:
        """Return total quarantined records."""

        return sum(result.quarantined_count for result in self.dataset_results.values())
