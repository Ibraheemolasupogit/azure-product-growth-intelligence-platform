"""Typed models for churn prediction."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from product_growth_intelligence.data_generation.models import Record

SnapshotCadence = Literal["once_per_user"]
ModelChoice = Literal["auto", "baseline", "logistic", "random_forest"]
ThresholdRule = Literal["validation_f1", "top_20_percent", "fixed_0_5"]


@dataclass(frozen=True)
class ChurnTrainingConfig:
    """Configuration for one deterministic churn training run."""

    input_dir: Path
    output_root: Path
    run_id: str | None = None
    analysis_start: str = "2025-01-01T00:00:00Z"
    analysis_end: str = "2025-06-30T23:59:59Z"
    lookback_days: int = 28
    label_window_days: int = 28
    snapshot_cadence: SnapshotCadence = "once_per_user"
    model: ModelChoice = "auto"
    random_seed: int = 1729
    selected_threshold_rule: ThresholdRule = "validation_f1"
    subgroup_threshold: int = 5
    fixed_run_time: str | None = None
    overwrite: bool = False
    validate_only: bool = False

    def validate(self) -> None:
        """Validate configuration values."""

        if self.lookback_days <= 0:
            msg = "lookback_days must be positive."
            raise ValueError(msg)
        if self.label_window_days <= 0:
            msg = "label_window_days must be positive."
            raise ValueError(msg)
        if self.snapshot_cadence != "once_per_user":
            msg = "Only once_per_user snapshot cadence is implemented in Milestone 6."
            raise ValueError(msg)
        if self.model not in {"auto", "baseline", "logistic", "random_forest"}:
            msg = f"Unsupported model: {self.model}."
            raise ValueError(msg)
        if self.selected_threshold_rule not in {"validation_f1", "top_20_percent", "fixed_0_5"}:
            msg = f"Unsupported threshold rule: {self.selected_threshold_rule}."
            raise ValueError(msg)
        if self.subgroup_threshold < 0:
            msg = "subgroup_threshold cannot be negative."
            raise ValueError(msg)


@dataclass(frozen=True)
class SnapshotLabel:
    """One point-in-time snapshot and future churn label."""

    snapshot_id: str
    user_id: str
    snapshot_timestamp: str
    feature_window_start: str
    feature_window_end: str
    label_window_start: str
    label_window_end: str
    behavioural_churn: int
    future_qualifying_events: int
    subscription_cancelled: int
    subscription_downgraded: int
    paid_inactive: int
    free_inactive: int

    def to_record(self) -> Record:
        """Return JSON-ready label record."""

        return {
            "snapshot_id": self.snapshot_id,
            "user_id": self.user_id,
            "snapshot_timestamp": self.snapshot_timestamp,
            "feature_window_start": self.feature_window_start,
            "feature_window_end": self.feature_window_end,
            "label_window_start": self.label_window_start,
            "label_window_end": self.label_window_end,
            "behavioural_churn": self.behavioural_churn,
            "future_qualifying_events": self.future_qualifying_events,
            "subscription_cancelled": self.subscription_cancelled,
            "subscription_downgraded": self.subscription_downgraded,
            "paid_inactive": self.paid_inactive,
            "free_inactive": self.free_inactive,
        }


@dataclass(frozen=True)
class FeatureRow:
    """Feature vector joined to a snapshot label."""

    label: SnapshotLabel
    features: Record

    def to_record(self) -> Record:
        """Return a flat matrix row."""

        return {
            "snapshot_id": self.label.snapshot_id,
            "user_id": self.label.user_id,
            "snapshot_timestamp": self.label.snapshot_timestamp,
            "behavioural_churn": self.label.behavioural_churn,
            **self.features,
        }


@dataclass(frozen=True)
class ChurnTrainingResult:
    """Completed churn model output paths and headline metrics."""

    run_id: str
    status: str
    output_dir: Path
    row_count: int
    selected_model: str
    selected_threshold: float
    label_prevalence: float
    validation_metrics: dict[str, object] = field(default_factory=dict)
    test_metrics: dict[str, object] = field(default_factory=dict)
