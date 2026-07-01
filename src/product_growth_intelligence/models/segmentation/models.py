"""Typed models for governed user segmentation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from product_growth_intelligence.data_generation.models import Record

SegmentationAlgorithm = Literal["kmeans"]


@dataclass(frozen=True)
class SegmentationConfig:
    """Configuration for one segmentation run."""

    input_dir: Path
    output_root: Path
    run_id: str | None = None
    snapshot_time: str = "2025-06-30T23:59:59Z"
    lookback_days: int = 56
    minimum_account_age: int = 14
    minimum_activity: int = 0
    include_inactive_users: bool = True
    max_snapshots_per_user: int = 1
    candidate_clusters: tuple[int, ...] = (2, 3, 4, 5, 6)
    cluster_count: int | None = None
    minimum_cluster_size: int = 1
    algorithm: SegmentationAlgorithm = "kmeans"
    random_seed: int = 1729
    kmeans_initialisations: int = 20
    stability_seeds: tuple[int, ...] = (1729, 1730, 1731)
    pca_components: int = 2
    suppression_threshold: int = 5
    fixed_run_time: str | None = None
    overwrite: bool = False
    validate_only: bool = False
    evidence_mode: bool = False

    def validate(self) -> None:
        """Validate configuration values."""

        if self.lookback_days <= 0:
            msg = "lookback_days must be positive."
            raise ValueError(msg)
        if self.minimum_account_age < 0:
            msg = "minimum_account_age cannot be negative."
            raise ValueError(msg)
        if self.minimum_activity < 0:
            msg = "minimum_activity cannot be negative."
            raise ValueError(msg)
        if self.max_snapshots_per_user != 1:
            msg = "Milestone 7 implements one latest snapshot per user."
            raise ValueError(msg)
        if self.algorithm != "kmeans":
            msg = f"Unsupported segmentation algorithm: {self.algorithm}."
            raise ValueError(msg)
        candidates = self.candidate_clusters
        if self.cluster_count is not None:
            candidates = (self.cluster_count,)
        if not candidates:
            msg = "candidate_clusters cannot be empty."
            raise ValueError(msg)
        if any(value < 2 for value in candidates):
            msg = "candidate cluster counts must be at least 2."
            raise ValueError(msg)
        if len(set(candidates)) != len(candidates):
            msg = "candidate cluster counts must be unique."
            raise ValueError(msg)
        if self.minimum_cluster_size <= 0:
            msg = "minimum_cluster_size must be positive."
            raise ValueError(msg)
        if self.kmeans_initialisations <= 0:
            msg = "kmeans_initialisations must be positive."
            raise ValueError(msg)
        if not self.stability_seeds:
            msg = "stability_seeds cannot be empty."
            raise ValueError(msg)
        if self.pca_components <= 0:
            msg = "pca_components must be positive."
            raise ValueError(msg)
        if self.suppression_threshold < 0:
            msg = "suppression_threshold cannot be negative."
            raise ValueError(msg)


@dataclass(frozen=True)
class SegmentationSnapshot:
    """One eligible user snapshot."""

    snapshot_id: str
    user_id: str
    snapshot_timestamp: str
    feature_window_start: str
    feature_window_end: str
    source_ingestion_run_id: str

    def to_record(self) -> Record:
        """Return JSON-ready snapshot fields."""

        return {
            "snapshot_id": self.snapshot_id,
            "user_id": self.user_id,
            "snapshot_timestamp": self.snapshot_timestamp,
            "feature_window_start": self.feature_window_start,
            "feature_window_end": self.feature_window_end,
            "source_ingestion_run_id": self.source_ingestion_run_id,
        }


@dataclass(frozen=True)
class SegmentationRow:
    """Features for one segmentation snapshot."""

    snapshot: SegmentationSnapshot
    features: Record

    def to_record(self) -> Record:
        """Return a flat feature-matrix row."""

        return {
            **self.snapshot.to_record(),
            **self.features,
        }


@dataclass(frozen=True)
class RuleAssignment:
    """Deterministic rule-based segment assignment."""

    snapshot_id: str
    user_id: str
    snapshot_timestamp: str
    rule_based_segment_id: str
    segment_name: str
    rule_version: str
    matched_rule: str
    reason_codes: tuple[str, ...]
    supporting_feature_summary: Record
    source_ingestion_run_id: str

    def to_record(self) -> Record:
        """Return CSV-ready assignment fields."""

        return {
            "snapshot_id": self.snapshot_id,
            "user_id": self.user_id,
            "snapshot_timestamp": self.snapshot_timestamp,
            "rule_based_segment_id": self.rule_based_segment_id,
            "segment_name": self.segment_name,
            "rule_version": self.rule_version,
            "matched_rule": self.matched_rule,
            "reason_codes": "|".join(self.reason_codes),
            "supporting_feature_summary": self.supporting_feature_summary,
            "source_ingestion_run_id": self.source_ingestion_run_id,
        }


@dataclass(frozen=True)
class SegmentationResult:
    """Completed segmentation outputs."""

    run_id: str
    status: str
    output_dir: Path
    eligible_snapshots: int
    selected_cluster_count: int
    selected_algorithm: str
    diagnostics: dict[str, object] = field(default_factory=dict)
