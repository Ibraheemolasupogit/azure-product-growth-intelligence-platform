"""Ingestion run ID and metadata helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from product_growth_intelligence.data_generation.models import Record
from product_growth_intelligence.ingestion.fingerprints import record_fingerprint
from product_growth_intelligence.ingestion.models import IngestionConfig, IngestionMetadata
from product_growth_intelligence.validation.contracts import CONTRACT_VERSION
from product_growth_intelligence.validation.rule_models import SourceLocation


def ingestion_time(config: IngestionConfig) -> str:
    """Return the operational or fixed ingestion timestamp."""

    if config.fixed_ingestion_time:
        return config.fixed_ingestion_time
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def derive_run_id(config: IngestionConfig) -> str:
    """Derive a deterministic run ID when one is not supplied."""

    if config.run_id:
        return config.run_id
    source_name = config.source.name or "source"
    basis = {
        "source": str(config.source),
        "mode": config.mode,
        "schema_policy": config.schema_policy,
        "duplicate_policy": config.duplicate_policy,
        "contract_version": config.contract_version,
    }
    return f"{config.mode}-{source_name}-{record_fingerprint(basis)[:12]}"


def attach_metadata(
    record: Record | None,
    *,
    run_id: str,
    dataset: str,
    source_file: str,
    source_location: SourceLocation,
    source_generation_run_id: str | None,
    status: str,
    rule_ids: tuple[str, ...],
    ingested_at: str,
) -> Record:
    """Attach nested ingestion metadata without changing business fields."""

    fingerprint = record_fingerprint(record) if record is not None else None
    metadata = IngestionMetadata(
        ingestion_run_id=run_id,
        source_dataset=dataset,
        source_file=source_file,
        source_row_number=source_location.row_number,
        source_line_number=source_location.line_number,
        source_generation_run_id=source_generation_run_id,
        ingested_at=ingested_at,
        contract_version=CONTRACT_VERSION,
        record_status=status,
        quality_rule_ids=rule_ids,
        record_fingerprint=fingerprint,
    )
    enriched: Record = dict(record or {})
    enriched["_ingestion_metadata"] = metadata.to_dict()
    return enriched
