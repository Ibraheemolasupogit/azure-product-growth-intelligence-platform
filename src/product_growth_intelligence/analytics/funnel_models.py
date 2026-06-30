"""Typed models for governed funnel analytics."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from product_growth_intelligence.data_generation.models import JsonValue, Record

AttemptStatus = Literal["completed", "abandoned", "incomplete", "censored"]
SequencePolicy = Literal["strict", "flexible"]
AttemptPolicy = Literal["first-entry"]
PercentileMethod = Literal["nearest-rank"]
DEFAULT_SEGMENT_DIMENSIONS = (
    "persona",
    "acquisition_channel",
    "region",
    "device_preference",
    "initial_plan",
    "company_size_band",
    "is_team_account",
    "experiment_variant",
)


@dataclass(frozen=True)
class FunnelStage:
    """One ordered funnel stage."""

    stage_id: str
    stage_name: str
    event_names: tuple[str, ...]
    minimum_event_count: int = 1
    subscription_paid_outcome: bool = False


@dataclass(frozen=True)
class FunnelDefinition:
    """Governed funnel definition."""

    funnel_id: str
    funnel_name: str
    version: str
    business_objective: str
    analytical_entity: str
    stages: tuple[FunnelStage, ...]
    allowed_completion_days: int
    eligibility_rule: str
    conversion_outcome: str
    supported_segments: tuple[str, ...]
    product_owner: str
    metric_notes: str

    @property
    def entry_stage(self) -> FunnelStage:
        """Return the entry stage."""

        return self.stages[0]

    @property
    def final_stage(self) -> FunnelStage:
        """Return the terminal stage."""

        return self.stages[-1]


@dataclass(frozen=True)
class FunnelAnalysisConfig:
    """Configuration for one funnel analysis run."""

    input_dir: Path
    output_root: Path
    run_id: str | None = None
    analysis_start: str = "2025-01-01T00:00:00Z"
    analysis_end: str = "2025-06-30T23:59:59Z"
    default_completion_window_days: int = 30
    attempt_policy: AttemptPolicy = "first-entry"
    sequence_policy: SequencePolicy = "strict"
    enabled_funnels: tuple[str, ...] = ()
    segment_dimensions: tuple[str, ...] = DEFAULT_SEGMENT_DIMENSIONS
    suppression_threshold: int = 5
    percentile_method: PercentileMethod = "nearest-rank"
    fixed_analysis_time: str | None = None
    overwrite: bool = False
    validate_only: bool = False
    evidence_mode: bool = False

    def validate(self, known_funnels: set[str]) -> None:
        """Validate analysis configuration."""

        if self.attempt_policy != "first-entry":
            msg = "Only first-entry attempt policy is implemented in Milestone 4."
            raise ValueError(msg)
        if self.sequence_policy not in {"strict", "flexible"}:
            msg = f"Unsupported sequence policy: {self.sequence_policy}."
            raise ValueError(msg)
        if self.default_completion_window_days <= 0:
            msg = "default_completion_window_days must be positive."
            raise ValueError(msg)
        if self.suppression_threshold < 0:
            msg = "suppression_threshold cannot be negative."
            raise ValueError(msg)
        unknown = set(self.enabled_funnels) - known_funnels
        if unknown:
            msg = f"Unknown funnel IDs: {', '.join(sorted(unknown))}."
            raise ValueError(msg)


@dataclass(frozen=True)
class TrustedInput:
    """Trusted accepted datasets plus ingestion lineage."""

    input_dir: Path
    ingestion_manifest: dict[str, JsonValue]
    source_manifest_checksum: str | None
    source_ingestion_run_id: str
    contract_versions: dict[str, str]
    datasets: dict[str, list[Record]]


@dataclass(frozen=True)
class StageMatch:
    """The event or subscription record that qualified a stage."""

    timestamp: str
    event_id: str
    session_id: str | None


@dataclass(frozen=True)
class FunnelAttempt:
    """Materialised first-entry funnel attempt."""

    attempt_id: str
    funnel_id: str
    funnel_version: str
    user_id: str
    entry_timestamp: str
    last_observed_timestamp: str
    completion_timestamp: str | None
    attempt_status: AttemptStatus
    highest_stage_reached: int
    stages_reached: tuple[str, ...]
    stage_timestamps: dict[str, str]
    stage_event_ids: dict[str, str]
    stage_session_ids: dict[str, str | None]
    sessions_involved: int
    repeated_event_counts: dict[str, int]
    error_events_before_exit: int
    segments: dict[str, JsonValue]
    source_ingestion_run_id: str

    def to_record(self) -> Record:
        """Return a JSONL-ready attempt record."""

        return {
            "attempt_id": self.attempt_id,
            "funnel_id": self.funnel_id,
            "funnel_version": self.funnel_version,
            "user_id": self.user_id,
            "entry_timestamp": self.entry_timestamp,
            "last_observed_timestamp": self.last_observed_timestamp,
            "completion_timestamp": self.completion_timestamp,
            "attempt_status": self.attempt_status,
            "highest_stage_reached": self.highest_stage_reached,
            "stages_reached": list(self.stages_reached),
            "stage_timestamps": self.stage_timestamps,
            "stage_event_ids": self.stage_event_ids,
            "stage_session_ids": self.stage_session_ids,
            "sessions_involved": self.sessions_involved,
            "repeated_event_counts": self.repeated_event_counts,
            "error_events_before_exit": self.error_events_before_exit,
            "segments": self.segments,
            "source_ingestion_run_id": self.source_ingestion_run_id,
        }


@dataclass
class FunnelAnalysisResult:
    """Completed analysis outputs."""

    run_id: str
    status: str
    output_dir: Path
    attempts: list[FunnelAttempt]
    summary_rows: list[Record] = field(default_factory=list)
    stage_rows: list[Record] = field(default_factory=list)
    segment_rows: list[Record] = field(default_factory=list)
    time_rows: list[Record] = field(default_factory=list)
    dropoff_rows: list[Record] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
