"""Trusted Milestone 3 input loading for funnel analytics."""

from __future__ import annotations

import json
from pathlib import Path

from product_growth_intelligence.analytics.funnel_models import TrustedInput
from product_growth_intelligence.data_generation.models import JsonValue, Record
from product_growth_intelligence.ingestion.fingerprints import file_sha256
from product_growth_intelligence.validation.contracts import CONTRACT_VERSION

REQUIRED_DATASETS = (
    "users",
    "sessions",
    "clickstream_events",
    "feature_usage",
    "subscriptions",
    "experiment_assignments",
)


def load_trusted_input(input_dir: Path) -> TrustedInput:
    """Load accepted Milestone 3 datasets after verifying ingestion metadata."""

    manifest_path = input_dir / "ingestion-manifest.json"
    if not manifest_path.exists():
        msg = f"Missing ingestion manifest: {manifest_path}."
        raise FileNotFoundError(msg)
    manifest_raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest_raw, dict):
        msg = "Ingestion manifest must be a JSON object."
        raise ValueError(msg)
    if manifest_raw.get("pipeline_status") != "passed":
        msg = "Funnel analytics require a passed Milestone 3 ingestion run."
        raise ValueError(msg)
    contract_versions = manifest_raw.get("contract_versions")
    if not isinstance(contract_versions, dict):
        msg = "Ingestion manifest is missing contract_versions."
        raise ValueError(msg)
    for dataset in REQUIRED_DATASETS:
        if contract_versions.get(dataset) != CONTRACT_VERSION:
            msg = f"Dataset {dataset} has incompatible contract version."
            raise ValueError(msg)

    accepted_dir = input_dir / "accepted"
    datasets: dict[str, list[Record]] = {}
    for dataset in REQUIRED_DATASETS:
        path = accepted_dir / f"{dataset}.jsonl"
        if not path.exists():
            msg = f"Missing accepted dataset: {path}."
            raise FileNotFoundError(msg)
        datasets[dataset] = _read_jsonl(path)

    return TrustedInput(
        input_dir=input_dir,
        ingestion_manifest=manifest_raw,
        source_manifest_checksum=_text_or_none(manifest_raw.get("parent_source_manifest_checksum")),
        source_ingestion_run_id=str(manifest_raw["ingestion_run_id"]),
        contract_versions={str(key): str(value) for key, value in contract_versions.items()},
        datasets=datasets,
    )


def source_manifest_checksum(input_dir: Path) -> str:
    """Return the checksum of the source ingestion manifest."""

    return file_sha256(input_dir / "ingestion-manifest.json")


def dataset_row_counts(trusted: TrustedInput) -> dict[str, int]:
    """Return loaded dataset row counts."""

    return {dataset: len(records) for dataset, records in trusted.datasets.items()}


def _read_jsonl(path: Path) -> list[Record]:
    records: list[Record] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    msg = f"Accepted dataset {path} contains a non-object record."
                    raise ValueError(msg)
                records.append(value)
    return records


def _text_or_none(value: JsonValue) -> str | None:
    return str(value) if value is not None else None
