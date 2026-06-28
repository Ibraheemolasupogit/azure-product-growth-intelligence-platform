"""Typed models for deterministic synthetic data generation."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, TypeAlias

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
Record: TypeAlias = dict[str, Any]


@dataclass(frozen=True)
class GenerationConfig:
    """Configuration for a synthetic data generation run."""

    profile: str
    user_count: int
    start_date: date
    end_date: date
    seed: int
    output_dir: Path
    timezone: str
    persona_distribution: dict[str, float]
    acquisition_channel_distribution: dict[str, float]
    country_distribution: dict[str, float]
    feedback_probability: float
    include_generation_timestamp: bool = False


@dataclass(frozen=True)
class GeneratedDatasets:
    """In-memory generated datasets."""

    users: list[Record]
    sessions: list[Record]
    clickstream_events: list[Record]
    feature_usage: list[Record]
    subscriptions: list[Record]
    experiment_assignments: list[Record]
    customer_feedback: list[Record]

    def by_name(self) -> dict[str, list[Record]]:
        """Return datasets keyed by output file name."""

        return {
            "users.csv": self.users,
            "sessions.jsonl": self.sessions,
            "clickstream_events.jsonl": self.clickstream_events,
            "feature_usage.csv": self.feature_usage,
            "subscriptions.csv": self.subscriptions,
            "experiment_assignments.csv": self.experiment_assignments,
            "customer_feedback.csv": self.customer_feedback,
        }


@dataclass(frozen=True)
class GenerationResult:
    """Result returned after writing generated data."""

    output_dir: Path
    manifest_path: Path
    row_counts: dict[str, int]


def utc_datetime(value: date) -> datetime:
    """Convert a date to midnight UTC."""

    return datetime(value.year, value.month, value.day, tzinfo=UTC)
