"""Typed models for retention and cohort analytics."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from product_growth_intelligence.data_generation.models import JsonValue, Record

TimeGrain = Literal["daily", "weekly", "monthly"]
LifecycleStatus = Literal[
    "new", "active", "inactive", "churned_descriptive", "resurrected", "censored"
]

DEFAULT_RETENTION_SEGMENTS = (
    "acquisition_channel",
    "persona",
    "region",
    "device_preference",
    "initial_plan",
    "current_plan",
    "company_size_band",
    "is_team_account",
    "activated",
    "collaboration_adopter",
    "automation_adopter",
    "recommendation_engaged",
    "paid_user",
)


@dataclass(frozen=True)
class ActivityRule:
    """Qualifying activity rule."""

    event_names: tuple[str, ...]
    minimum_event_count: int = 1
    minimum_active_days: int = 1


@dataclass(frozen=True)
class RetentionDefinition:
    """Governed retention definition."""

    definition_id: str
    name: str
    version: str
    business_objective: str
    anchor_rule: str
    eligibility_rule: str
    activity_rule: ActivityRule
    time_grain: TimeGrain
    maximum_horizon: int
    inactivity_threshold_periods: int
    churn_threshold_periods: int
    resurrection_rule: str
    supported_segments: tuple[str, ...]
    metric_notes: str
    owner: str


@dataclass(frozen=True)
class RetentionAnalysisConfig:
    """Configuration for retention analysis."""

    input_dir: Path
    output_root: Path
    run_id: str | None = None
    enabled_definitions: tuple[str, ...] = ()
    time_grain: TimeGrain = "weekly"
    analysis_start: str = "2025-01-01T00:00:00Z"
    analysis_end: str = "2025-06-30T23:59:59Z"
    horizon: int = 8
    segment_dimensions: tuple[str, ...] = DEFAULT_RETENTION_SEGMENTS
    suppression_threshold: int = 5
    inactivity_threshold: int = 2
    churn_threshold: int = 4
    fixed_analysis_time: str | None = None
    overwrite: bool = False
    validate_only: bool = False
    evidence_mode: bool = False

    def validate(self, known_definitions: set[str]) -> None:
        """Validate analysis settings."""

        if self.time_grain not in {"daily", "weekly", "monthly"}:
            msg = f"Unsupported time grain: {self.time_grain}."
            raise ValueError(msg)
        if self.horizon < 0:
            msg = "horizon must be non-negative."
            raise ValueError(msg)
        if self.suppression_threshold < 0:
            msg = "suppression_threshold cannot be negative."
            raise ValueError(msg)
        if self.inactivity_threshold <= 0 or self.churn_threshold <= 0:
            msg = "inactivity and churn thresholds must be positive."
            raise ValueError(msg)
        if self.churn_threshold < self.inactivity_threshold:
            msg = "churn threshold cannot be below inactivity threshold."
            raise ValueError(msg)
        unknown = set(self.enabled_definitions) - known_definitions
        if unknown:
            msg = f"Unknown retention definitions: {', '.join(sorted(unknown))}."
            raise ValueError(msg)


@dataclass(frozen=True)
class CohortMembership:
    """One user assigned to one retention definition."""

    membership_id: str
    definition_id: str
    definition_version: str
    user_id: str
    anchor_timestamp: str
    cohort_period: str
    segments: dict[str, JsonValue]
    source_ingestion_run_id: str

    def to_record(self) -> Record:
        """Return JSONL-ready record."""

        return {
            "membership_id": self.membership_id,
            "definition_id": self.definition_id,
            "definition_version": self.definition_version,
            "user_id": self.user_id,
            "anchor_timestamp": self.anchor_timestamp,
            "cohort_period": self.cohort_period,
            "segments": self.segments,
            "source_ingestion_run_id": self.source_ingestion_run_id,
        }


@dataclass(frozen=True)
class UserPeriodActivity:
    """One user-definition-period observation."""

    membership_id: str
    definition_id: str
    user_id: str
    cohort_period: str
    period_index: int
    period_start: str
    period_end: str
    observed: bool
    active: bool
    qualifying_event_count: int
    active_days: int

    def to_record(self) -> Record:
        """Return JSONL-ready record."""

        return self.__dict__.copy()


@dataclass
class RetentionAnalysisResult:
    """Completed retention analysis."""

    run_id: str
    status: str
    output_dir: Path
    memberships: list[CohortMembership]
    user_periods: list[UserPeriodActivity]
    retention_long_rows: list[Record] = field(default_factory=list)
    cohort_summary_rows: list[Record] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
