"""Typed models for governed recommendation baselines."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

RecommendationModel = Literal[
    "global_popularity",
    "recent_popularity",
    "segment_popularity",
    "item_item_cf",
]


@dataclass(frozen=True)
class RecommendationConfig:
    """Configuration for one recommendation run."""

    input_dir: Path
    output_root: Path
    run_id: str | None = None
    snapshot_time: str = "2025-03-31T23:59:59Z"
    lookback_days: int = 56
    holdout_days: int = 28
    minimum_user_interactions: int = 1
    minimum_item_interactions: int = 1
    top_k: tuple[int, ...] = (1, 3, 5, 10)
    popularity_window_days: int = 56
    recent_popularity_window_days: int = 14
    enabled_models: tuple[RecommendationModel, ...] = (
        "global_popularity",
        "recent_popularity",
        "segment_popularity",
        "item_item_cf",
    )
    use_segments: bool = True
    segment_input: Path | None = None
    minimum_user_coverage: float = 0.5
    minimum_catalogue_coverage: float = 0.1
    minimum_similarity_support: int = 1
    novelty_smoothing: float = 1.0
    random_seed: int = 1729
    fixed_run_time: str | None = None
    overwrite: bool = False
    validate_only: bool = False
    evidence_mode: bool = False

    def validate(self) -> None:
        """Validate configuration values."""

        if self.lookback_days <= 0:
            msg = "lookback_days must be positive."
            raise ValueError(msg)
        if self.holdout_days <= 0:
            msg = "holdout_days must be positive."
            raise ValueError(msg)
        if self.minimum_user_interactions < 0:
            msg = "minimum_user_interactions cannot be negative."
            raise ValueError(msg)
        if self.minimum_item_interactions < 0:
            msg = "minimum_item_interactions cannot be negative."
            raise ValueError(msg)
        if not self.top_k or any(value <= 0 for value in self.top_k):
            msg = "top_k values must be positive."
            raise ValueError(msg)
        if len(set(self.top_k)) != len(self.top_k):
            msg = "top_k values must be unique."
            raise ValueError(msg)
        if self.popularity_window_days <= 0 or self.recent_popularity_window_days <= 0:
            msg = "popularity windows must be positive."
            raise ValueError(msg)
        if any(
            model
            not in {
                "global_popularity",
                "recent_popularity",
                "segment_popularity",
                "item_item_cf",
            }
            for model in self.enabled_models
        ):
            msg = "Unsupported recommendation model."
            raise ValueError(msg)
        if not 0 <= self.minimum_user_coverage <= 1:
            msg = "minimum_user_coverage must be between zero and one."
            raise ValueError(msg)
        if not 0 <= self.minimum_catalogue_coverage <= 1:
            msg = "minimum_catalogue_coverage must be between zero and one."
            raise ValueError(msg)
        if self.minimum_similarity_support < 0:
            msg = "minimum_similarity_support cannot be negative."
            raise ValueError(msg)
        if self.novelty_smoothing <= 0:
            msg = "novelty_smoothing must be positive."
            raise ValueError(msg)


@dataclass(frozen=True)
class RecommendationResult:
    """Completed recommendation run summary."""

    run_id: str
    status: str
    output_dir: Path
    eligible_users: int
    evaluated_users: int
    selected_model: str
    diagnostics: dict[str, object] = field(default_factory=dict)
