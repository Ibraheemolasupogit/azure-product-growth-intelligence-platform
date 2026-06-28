"""Deterministic CSV, JSONL, and manifest writers."""

import csv
import hashlib
import json
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile

from product_growth_intelligence.data_generation.models import (
    GeneratedDatasets,
    GenerationConfig,
    GenerationResult,
    JsonValue,
    Record,
)

GENERATOR_VERSION = "0.2.0"
CONTRACT_VERSION = "2026-06-milestone-2"

CSV_COLUMNS = {
    "users.csv": (
        "user_id",
        "signup_timestamp",
        "country",
        "region",
        "acquisition_channel",
        "device_preference",
        "persona",
        "company_size_band",
        "initial_plan",
        "marketing_consent",
        "is_team_account",
        "synthetic_record",
    ),
    "feature_usage.csv": (
        "usage_id",
        "user_id",
        "observation_date",
        "feature_name",
        "usage_count",
        "active_minutes",
        "successful_action_count",
        "error_count",
        "synthetic_record",
    ),
    "subscriptions.csv": (
        "subscription_id",
        "user_id",
        "plan_name",
        "billing_cycle",
        "status",
        "period_start_timestamp",
        "period_end_timestamp",
        "trial_start_timestamp",
        "trial_end_timestamp",
        "monthly_recurring_revenue",
        "cancellation_reason",
        "synthetic_record",
    ),
    "experiment_assignments.csv": (
        "assignment_id",
        "experiment_id",
        "user_id",
        "variant",
        "assignment_timestamp",
        "eligibility_segment",
        "exposure_timestamp",
        "conversion_timestamp",
        "converted",
        "synthetic_record",
    ),
    "customer_feedback.csv": (
        "feedback_id",
        "user_id",
        "feedback_timestamp",
        "feedback_channel",
        "rating",
        "feedback_text",
        "feedback_theme",
        "feature_name",
        "synthetic_sentiment_label",
        "synthetic_record",
    ),
}

JSONL_COLUMNS = {
    "sessions.jsonl": (
        "session_id",
        "user_id",
        "session_start_timestamp",
        "session_end_timestamp",
        "device_type",
        "operating_system",
        "traffic_source",
        "country",
        "event_count",
        "session_duration_seconds",
        "synthetic_record",
    ),
    "clickstream_events.jsonl": (
        "event_id",
        "session_id",
        "user_id",
        "event_timestamp",
        "event_name",
        "feature_name",
        "page_name",
        "journey_stage",
        "device_type",
        "event_sequence_number",
        "experiment_id",
        "experiment_variant",
        "recommendation_id",
        "properties",
        "synthetic_record",
    ),
}


def write_datasets(
    datasets: GeneratedDatasets, config: GenerationConfig, overwrite: bool = False
) -> GenerationResult:
    """Write generated datasets and a deterministic manifest."""

    output_dir = config.output_dir
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        msg = f"Output directory {output_dir} already exists and is not empty. Pass --overwrite."
        raise FileExistsError(msg)
    output_dir.mkdir(parents=True, exist_ok=True)

    for file_name, records in datasets.by_name().items():
        path = output_dir / file_name
        if file_name.endswith(".csv"):
            _write_csv(path, records, CSV_COLUMNS[file_name])
        else:
            _write_jsonl(path, records, JSONL_COLUMNS[file_name])

    manifest = _build_manifest(datasets, config)
    manifest_path = output_dir / "manifest.json"
    _atomic_write_text(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return GenerationResult(
        output_dir=output_dir,
        manifest_path=manifest_path,
        row_counts={name: len(records) for name, records in datasets.by_name().items()},
    )


def _write_csv(path: Path, records: list[Record], columns: Iterable[str]) -> None:
    columns_tuple = tuple(columns)
    with NamedTemporaryFile(
        "w", encoding="utf-8", newline="", delete=False, dir=path.parent
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=columns_tuple, extrasaction="raise", lineterminator="\n"
        )
        writer.writeheader()
        for record in records:
            writer.writerow({column: _csv_value(record.get(column)) for column in columns_tuple})
        temporary_path = Path(handle.name)
    temporary_path.replace(path)


def _write_jsonl(path: Path, records: list[Record], columns: Iterable[str]) -> None:
    columns_tuple = tuple(columns)
    with NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", delete=False, dir=path.parent
    ) as handle:
        for record in records:
            ordered = {column: record.get(column) for column in columns_tuple}
            handle.write(
                json.dumps(ordered, default=_json_default, sort_keys=True, separators=(",", ":"))
            )
            handle.write("\n")
        temporary_path = Path(handle.name)
    temporary_path.replace(path)


def _build_manifest(datasets: GeneratedDatasets, config: GenerationConfig) -> dict[str, JsonValue]:
    dataset_entries: dict[str, JsonValue] = {}
    for file_name, records in datasets.by_name().items():
        path = config.output_dir / file_name
        dataset_entries[file_name] = {
            "row_count": len(records),
            "relative_path": file_name,
            "sha256": _sha256(path),
        }

    return {
        "run_id": config.output_dir.name,
        "generator_version": GENERATOR_VERSION,
        "generation_profile": config.profile,
        "seed": config.seed,
        "simulation_period": {
            "start_date": config.start_date.isoformat(),
            "end_date": config.end_date.isoformat(),
            "timezone": config.timezone,
        },
        "created_at": None,
        "contract_version": CONTRACT_VERSION,
        "datasets": dataset_entries,
    }


def _atomic_write_text(path: Path, content: str) -> None:
    with NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", delete=False, dir=path.parent
    ) as handle:
        handle.write(content)
        temporary_path = Path(handle.name)
    temporary_path.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _csv_value(value: object) -> object:
    if value is None:
        return ""
    return value


def _json_default(value: object) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    msg = f"Object of type {type(value).__name__} is not JSON serialisable."
    raise TypeError(msg)
