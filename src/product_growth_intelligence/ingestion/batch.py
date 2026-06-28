"""Local batch ingestion pipeline for NexaFlow datasets."""

from __future__ import annotations

import json
from pathlib import Path

from product_growth_intelligence.data_generation.models import JsonValue, Record
from product_growth_intelligence.ingestion.fingerprints import file_sha256
from product_growth_intelligence.ingestion.metadata import (
    attach_metadata,
    derive_run_id,
    ingestion_time,
)
from product_growth_intelligence.ingestion.models import (
    DatasetIngestionResult,
    IngestionConfig,
    ParsedRecord,
    PipelineResult,
)
from product_growth_intelligence.ingestion.parsers import parse_dataset
from product_growth_intelligence.ingestion.writers import (
    make_pipeline_result,
    prepare_output_dirs,
    write_dataset_outputs,
    write_lineage,
    write_manifest,
    write_metrics,
    write_quality_outputs,
)
from product_growth_intelligence.validation.contracts import (
    CONTRACTS,
    SUPPORTED_SOURCE_CONTRACTS,
    DatasetContract,
)
from product_growth_intelligence.validation.cross_dataset import validate_cross_dataset
from product_growth_intelligence.validation.rule_models import (
    RuleResult,
    SourceLocation,
    failed_rule,
)
from product_growth_intelligence.validation.rules import validate_record


def run_batch_ingestion(config: IngestionConfig) -> PipelineResult:
    """Run local batch ingestion for all required datasets."""

    config.validate()
    if not config.source.exists() or not config.source.is_dir():
        msg = f"Source directory {config.source} does not exist."
        raise FileNotFoundError(msg)
    run_id = derive_run_id(config)
    output_dir, quality_dir = prepare_output_dirs(config, run_id)
    ingested_at = ingestion_time(config)
    source_manifest, source_manifest_checksum, manifest_rules = _read_source_manifest(config)
    source_generation_run_id = _manifest_text(source_manifest, "run_id")

    dataset_results: dict[str, DatasetIngestionResult] = {}
    all_rules: list[RuleResult] = list(manifest_rules)
    input_checksums: dict[str, str] = {}

    for dataset, contract in CONTRACTS.items():
        result = _process_dataset(
            config,
            contract,
            run_id,
            ingested_at,
            source_generation_run_id,
            source_manifest,
        )
        dataset_results[dataset] = result
        all_rules.extend(result.rules)
        path = config.source / contract.filename
        if path.exists():
            input_checksums[contract.filename] = file_sha256(path)

    _apply_cross_dataset_rules(dataset_results, all_rules)
    _enforce_duplicate_policy(
        config, dataset_results, all_rules, run_id, ingested_at, source_generation_run_id
    )
    _refresh_counts(dataset_results)
    all_rules = [*all_rules, *_threshold_rules(config, dataset_results)]
    status = _status_for(all_rules)

    if config.validate_only:
        return make_pipeline_result(
            run_id=run_id,
            status=status,
            output_dir=output_dir,
            quality_dir=quality_dir,
            dataset_results=dataset_results,
            manifest_path=None,
            quality_report_json_path=None,
            quality_report_md_path=None,
            lineage_path=None,
            metrics_path=None,
        )

    output_checksums: dict[str, str] = {}
    for result in dataset_results.values():
        output_checksums.update(write_dataset_outputs(output_dir, result))
    quality_json, quality_md = write_quality_outputs(
        quality_dir,
        run_id=run_id,
        status=status,
        dataset_results=dataset_results,
        all_rules=all_rules,
    )
    lineage_path = write_lineage(output_dir, dataset_results)
    metrics_path = write_metrics(
        quality_dir,
        files_discovered=len(input_checksums),
        dataset_results=dataset_results,
    )
    manifest_path = write_manifest(
        output_dir,
        run_id=run_id,
        status=status,
        config=config,
        source_generation_run_id=source_generation_run_id,
        input_checksums=input_checksums,
        output_checksums=output_checksums,
        dataset_results=dataset_results,
        source_manifest_checksum=source_manifest_checksum,
    )
    return make_pipeline_result(
        run_id=run_id,
        status=status,
        output_dir=output_dir,
        quality_dir=quality_dir,
        dataset_results=dataset_results,
        manifest_path=manifest_path,
        quality_report_json_path=quality_json,
        quality_report_md_path=quality_md,
        lineage_path=lineage_path,
        metrics_path=metrics_path,
    )


def _process_dataset(
    config: IngestionConfig,
    contract: DatasetContract,
    run_id: str,
    ingested_at: str,
    source_generation_run_id: str | None,
    source_manifest: dict[str, JsonValue] | None,
) -> DatasetIngestionResult:
    path = config.source / contract.filename
    result = DatasetIngestionResult(dataset=contract.dataset)
    if not path.exists():
        result.rules.append(
            failed_rule(
                "FILE_REQUIRED_MISSING",
                "Required dataset file exists",
                "critical",
                "file_integrity",
                contract.dataset,
                f"Required source file {contract.filename} is missing.",
                source_location=SourceLocation(contract.filename),
                remediation="Place the required dataset in the raw run directory.",
            )
        )
        return result

    result.rules.extend(_manifest_dataset_rules(config, contract, source_manifest))
    parsed_records, schema_findings, file_rules = parse_dataset(
        config.source, contract, config.schema_policy
    )
    result.schema_drift.extend(schema_findings)
    result.rules.extend(file_rules)
    result.source_count = len(parsed_records)
    for parsed in parsed_records:
        _classify_record(result, parsed, contract, run_id, ingested_at, source_generation_run_id)
    return result


def _classify_record(
    result: DatasetIngestionResult,
    parsed: ParsedRecord,
    contract: DatasetContract,
    run_id: str,
    ingested_at: str,
    source_generation_run_id: str | None,
) -> None:
    failures = list(parsed.parse_errors)
    if parsed.record is not None:
        failures.extend(validate_record(contract, parsed.record, parsed.source_location))
    result.rules.extend(failures)
    if failures or parsed.record is None:
        result.quarantined.append(
            {
                "raw_record": parsed.raw_record,
                "normalised_record": parsed.record,
                "failed_rules": [rule.to_dict() for rule in failures],
                "_ingestion_metadata": attach_metadata(
                    parsed.record,
                    run_id=run_id,
                    dataset=parsed.dataset,
                    source_file=parsed.source_file,
                    source_location=parsed.source_location,
                    source_generation_run_id=source_generation_run_id,
                    status="quarantined",
                    rule_ids=tuple(rule.rule_id for rule in failures),
                    ingested_at=ingested_at,
                )["_ingestion_metadata"],
            }
        )
        return
    result.accepted.append(
        attach_metadata(
            parsed.record,
            run_id=run_id,
            dataset=parsed.dataset,
            source_file=parsed.source_file,
            source_location=parsed.source_location,
            source_generation_run_id=source_generation_run_id,
            status="accepted",
            rule_ids=(),
            ingested_at=ingested_at,
        )
    )


def _apply_cross_dataset_rules(
    dataset_results: dict[str, DatasetIngestionResult],
    all_rules: list[RuleResult],
) -> None:
    datasets = {dataset: result.accepted for dataset, result in dataset_results.items()}
    cross_rules = validate_cross_dataset(datasets)
    all_rules.extend(cross_rules)
    for rule in cross_rules:
        result = dataset_results[rule.dataset]
        result.rules.append(rule)
        _quarantine_cross_failed_record(result, rule)


def _quarantine_cross_failed_record(result: DatasetIngestionResult, rule: RuleResult) -> None:
    if rule.source_location is None:
        return
    retained: list[Record] = []
    moved = False
    for record in result.accepted:
        metadata = record.get("_ingestion_metadata")
        if not isinstance(metadata, dict):
            retained.append(record)
            continue
        matches = (
            metadata.get("source_file") == rule.source_location.file_name
            and metadata.get("source_row_number") == rule.source_location.row_number
            and metadata.get("source_line_number") == rule.source_location.line_number
        )
        if matches and not moved:
            quarantined = dict(record)
            quarantined["_ingestion_metadata"] = {
                **dict(metadata),
                "record_status": "quarantined",
                "quality_rule_ids": [rule.rule_id],
            }
            result.quarantined.append(
                {
                    "raw_record": record,
                    "normalised_record": record,
                    "failed_rules": [rule.to_dict()],
                    "_ingestion_metadata": quarantined["_ingestion_metadata"],
                }
            )
            moved = True
        else:
            retained.append(record)
    result.accepted = retained


def _enforce_duplicate_policy(
    config: IngestionConfig,
    dataset_results: dict[str, DatasetIngestionResult],
    all_rules: list[RuleResult],
    run_id: str,
    ingested_at: str,
    source_generation_run_id: str | None,
) -> None:
    for dataset, result in dataset_results.items():
        contract = CONTRACTS[dataset]
        seen: dict[str, Record] = {}
        output: list[Record] = []
        duplicates: list[Record] = []
        for record in result.accepted:
            key = str(record[contract.primary_key])
            if key in seen:
                duplicates.append(record)
                rule = failed_rule(
                    "DUPLICATE_PRIMARY_KEY",
                    "Business primary keys are unique",
                    "error" if config.duplicate_policy == "reject" else "warning",
                    "uniqueness",
                    dataset,
                    f"Duplicate primary key {key}.",
                    field_name=contract.primary_key,
                    offending_value=key,
                )
                result.rules.append(rule)
                all_rules.append(rule)
                if config.duplicate_policy == "keep-last":
                    output = [row for row in output if str(row[contract.primary_key]) != key]
                    output.append(record)
                elif config.duplicate_policy == "reject":
                    result.quarantined.append(
                        _duplicate_quarantine(
                            record, rule, run_id, ingested_at, source_generation_run_id
                        )
                    )
                continue
            seen[key] = record
            output.append(record)
        if config.duplicate_policy == "reject":
            duplicate_keys = {str(row[contract.primary_key]) for row in duplicates}
            result.accepted = [
                row for row in output if str(row[contract.primary_key]) not in duplicate_keys
            ]
        else:
            result.accepted = output


def _duplicate_quarantine(
    record: Record,
    rule: RuleResult,
    run_id: str,
    ingested_at: str,
    source_generation_run_id: str | None,
) -> Record:
    metadata = record.get("_ingestion_metadata")
    source_file = str(metadata.get("source_file")) if isinstance(metadata, dict) else "unknown"
    location = SourceLocation(source_file)
    return {
        "raw_record": record,
        "normalised_record": record,
        "failed_rules": [rule.to_dict()],
        "_ingestion_metadata": attach_metadata(
            record,
            run_id=run_id,
            dataset=rule.dataset,
            source_file=source_file,
            source_location=location,
            source_generation_run_id=source_generation_run_id,
            status="quarantined",
            rule_ids=(rule.rule_id,),
            ingested_at=ingested_at,
        )["_ingestion_metadata"],
    }


def _read_source_manifest(
    config: IngestionConfig,
) -> tuple[dict[str, JsonValue] | None, str | None, list[RuleResult]]:
    path = config.source / "manifest.json"
    if not path.exists():
        return None, None, []
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return (
            None,
            None,
            [
                failed_rule(
                    "MANIFEST_INVALID_JSON",
                    "Source manifest is valid JSON",
                    "critical",
                    "file_integrity",
                    "manifest",
                    f"manifest.json is invalid JSON: {exc.msg}.",
                    source_location=SourceLocation("manifest.json"),
                )
            ],
        )
    if not isinstance(manifest, dict):
        return (
            None,
            None,
            [
                failed_rule(
                    "MANIFEST_INVALID_STRUCTURE",
                    "Source manifest is an object",
                    "critical",
                    "file_integrity",
                    "manifest",
                    "manifest.json must contain a JSON object.",
                    source_location=SourceLocation("manifest.json"),
                )
            ],
        )
    rules = []
    contract_version = manifest.get("contract_version")
    if str(contract_version) not in SUPPORTED_SOURCE_CONTRACTS:
        rules.append(
            failed_rule(
                "CONTRACT_VERSION_UNSUPPORTED",
                "Source contract version is supported",
                "critical",
                "file_integrity",
                "manifest",
                f"Unsupported source contract version: {contract_version}.",
                source_location=SourceLocation("manifest.json"),
            )
        )
    return manifest, file_sha256(path), rules


def _manifest_dataset_rules(
    config: IngestionConfig,
    contract: DatasetContract,
    manifest: dict[str, JsonValue] | None,
) -> list[RuleResult]:
    if manifest is None:
        return []
    datasets = manifest.get("datasets")
    if not isinstance(datasets, dict) or contract.filename not in datasets:
        return [
            failed_rule(
                "MANIFEST_DATASET_MISSING",
                "Manifest references expected datasets",
                "error",
                "file_integrity",
                contract.dataset,
                f"manifest.json does not reference {contract.filename}.",
                source_location=SourceLocation("manifest.json"),
            )
        ]
    entry = datasets[contract.filename]
    if not isinstance(entry, dict):
        return []
    rules: list[RuleResult] = []
    expected_sha = entry.get("sha256")
    path = config.source / contract.filename
    if isinstance(expected_sha, str) and file_sha256(path) != expected_sha:
        rules.append(
            failed_rule(
                "MANIFEST_CHECKSUM_MISMATCH",
                "Manifest checksum matches source file",
                "critical" if config.checksum_enforcement else "warning",
                "file_integrity",
                contract.dataset,
                f"Checksum mismatch for {contract.filename}.",
                source_location=SourceLocation(contract.filename),
            )
        )
    expected_rows = entry.get("row_count")
    if isinstance(expected_rows, int):
        actual_rows = _count_records(path, contract)
        if actual_rows != expected_rows:
            rules.append(
                failed_rule(
                    "MANIFEST_ROW_COUNT_MISMATCH",
                    "Manifest row count matches parsed records",
                    "error",
                    "file_integrity",
                    contract.dataset,
                    f"Manifest expected {expected_rows} rows but found {actual_rows}.",
                    source_location=SourceLocation(contract.filename),
                )
            )
    return rules


def _count_records(path: Path, contract: DatasetContract) -> int:
    if contract.file_format == "csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return max(sum(1 for _ in handle) - 1, 0)
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def _manifest_text(manifest: dict[str, JsonValue] | None, key: str) -> str | None:
    if manifest is None:
        return None
    value = manifest.get(key)
    return str(value) if value is not None else None


def _threshold_rules(
    config: IngestionConfig, dataset_results: dict[str, DatasetIngestionResult]
) -> list[RuleResult]:
    source_total = sum(result.source_count for result in dataset_results.values())
    quarantine_total = sum(result.quarantined_count for result in dataset_results.values())
    critical_total = sum(
        1
        for result in dataset_results.values()
        for rule in result.rules
        if not rule.passed and rule.severity == "critical"
    )
    rules: list[RuleResult] = []
    rate = quarantine_total / source_total if source_total else 0
    if rate > config.max_quarantine_rate:
        rules.append(
            failed_rule(
                "THRESHOLD_QUARANTINE_RATE_EXCEEDED",
                "Quarantine rate is within threshold",
                "critical",
                "consistency",
                "pipeline",
                f"Quarantine rate {rate:.6f} exceeds threshold {config.max_quarantine_rate:.6f}.",
            )
        )
    if critical_total > config.max_critical_failures:
        rules.append(
            failed_rule(
                "THRESHOLD_CRITICAL_FAILURES_EXCEEDED",
                "Critical failures are within threshold",
                "critical",
                "consistency",
                "pipeline",
                (
                    f"Critical failures {critical_total} exceed threshold "
                    f"{config.max_critical_failures}."
                ),
            )
        )
    return rules


def _status_for(rules: list[RuleResult]) -> str:
    failed = [rule for rule in rules if not rule.passed]
    if any(rule.severity in {"error", "critical"} for rule in failed):
        return "failed"
    if failed:
        return "passed_with_warnings"
    return "passed"


def _refresh_counts(dataset_results: dict[str, DatasetIngestionResult]) -> None:
    for result in dataset_results.values():
        result.accepted_count = len(result.accepted)
        result.quarantined_count = len(result.quarantined)
