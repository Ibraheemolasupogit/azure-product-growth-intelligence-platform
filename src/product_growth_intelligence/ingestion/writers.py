"""Writers for accepted, quarantine, quality, lineage, and manifest artefacts."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from product_growth_intelligence.data_generation.models import JsonValue, Record
from product_growth_intelligence.ingestion.fingerprints import file_sha256, record_fingerprint
from product_growth_intelligence.ingestion.models import (
    DatasetIngestionResult,
    IngestionConfig,
    PipelineResult,
)
from product_growth_intelligence.metadata import get_project_metadata
from product_growth_intelligence.validation.contracts import CONTRACT_VERSION, CONTRACTS
from product_growth_intelligence.validation.rule_models import RuleResult


def prepare_output_dirs(config: IngestionConfig, run_id: str) -> tuple[Path, Path]:
    """Create output directories or refuse to overwrite existing runs."""

    output_dir = config.output_root / run_id
    quality_dir = config.quality_root / run_id
    for path in (output_dir, quality_dir):
        if path.exists() and any(path.iterdir()) and not config.overwrite:
            msg = f"Output directory {path} already exists and is not empty. Pass --overwrite."
            raise FileExistsError(msg)
        path.mkdir(parents=True, exist_ok=True)
    (output_dir / "accepted").mkdir(exist_ok=True)
    (output_dir / "quarantine").mkdir(exist_ok=True)
    return output_dir, quality_dir


def write_dataset_outputs(output_dir: Path, result: DatasetIngestionResult) -> dict[str, str]:
    """Write accepted and quarantine records as canonical JSONL."""

    accepted_path = output_dir / "accepted" / f"{result.dataset}.jsonl"
    quarantine_path = output_dir / "quarantine" / f"{result.dataset}.jsonl"
    _write_jsonl(accepted_path, result.accepted)
    _write_jsonl(quarantine_path, result.quarantined)
    checksums = {
        f"accepted/{result.dataset}.jsonl": file_sha256(accepted_path),
        f"quarantine/{result.dataset}.jsonl": file_sha256(quarantine_path),
    }
    return checksums


def write_quality_outputs(
    quality_dir: Path,
    *,
    run_id: str,
    status: str,
    dataset_results: dict[str, DatasetIngestionResult],
    all_rules: list[RuleResult],
) -> tuple[Path, Path]:
    """Write JSON and Markdown quality reports."""

    report = build_quality_report(run_id, status, dataset_results, all_rules)
    json_path = quality_dir / "quality-report.json"
    md_path = quality_dir / "quality-report.md"
    _atomic_write(json_path, json.dumps(report, indent=2, sort_keys=True) + "\n")
    _atomic_write(md_path, _quality_markdown(report))
    return json_path, md_path


def build_quality_report(
    run_id: str,
    status: str,
    dataset_results: dict[str, DatasetIngestionResult],
    all_rules: list[RuleResult],
) -> dict[str, JsonValue]:
    """Build the machine-readable quality report."""

    failed_rules = [rule for rule in all_rules if not rule.passed]
    counts_by_severity = Counter(rule.severity for rule in failed_rules)
    top_failed = Counter(rule.rule_id for rule in failed_rules).most_common(10)
    datasets: dict[str, JsonValue] = {}
    for dataset, result in dataset_results.items():
        pass_rate = result.accepted_count / result.source_count if result.source_count else 1.0
        schema_drift: list[JsonValue] = [
            {
                "dataset": finding.dataset,
                "drift_type": finding.drift_type,
                "field_name": finding.field_name,
                "severity": finding.severity,
                "message": finding.message,
            }
            for finding in result.schema_drift
        ]
        datasets[dataset] = {
            "source_records": result.source_count,
            "accepted_records": result.accepted_count,
            "quarantined_records": result.quarantined_count,
            "pass_rate": round(pass_rate, 6),
            "schema_drift": schema_drift,
            "failed_rule_count": len([rule for rule in result.rules if not rule.passed]),
        }
    return {
        "run_id": run_id,
        "overall_status": status,
        "status_logic": (
            "passed means no errors or warnings; passed_with_warnings means only warnings; "
            "failed means at least one error/critical failure or threshold breach."
        ),
        "summary": {
            "source_records": sum(result.source_count for result in dataset_results.values()),
            "accepted_records": sum(result.accepted_count for result in dataset_results.values()),
            "quarantined_records": sum(
                result.quarantined_count for result in dataset_results.values()
            ),
            "warning_count": counts_by_severity["warning"],
            "error_count": counts_by_severity["error"],
            "critical_count": counts_by_severity["critical"],
        },
        "datasets": datasets,
        "top_failed_rules": [
            {"rule_id": str(rule_id), "count": count} for rule_id, count in top_failed
        ],
        "rule_results": [rule.to_dict() for rule in failed_rules],
        "remediation": (
            "Inspect quarantine JSONL records, correct malformed source extracts, "
            "and rerun with the same run ID plus --overwrite once the source is fixed."
        ),
    }


def write_manifest(
    output_dir: Path,
    *,
    run_id: str,
    status: str,
    config: IngestionConfig,
    source_generation_run_id: str | None,
    input_checksums: dict[str, str],
    output_checksums: dict[str, str],
    dataset_results: dict[str, DatasetIngestionResult],
    source_manifest_checksum: str | None,
) -> Path:
    """Write the ingestion manifest last."""

    manifest = {
        "ingestion_run_id": run_id,
        "source_generation_run_id": source_generation_run_id,
        "ingestion_mode": config.mode,
        "source_directory": str(config.source),
        "target_directory": str(output_dir),
        "fixed_ingestion_timestamp": config.fixed_ingestion_time,
        "contract_versions": {dataset: CONTRACT_VERSION for dataset in CONTRACTS},
        "schema_drift_policy": config.schema_policy,
        "duplicate_policy": config.duplicate_policy,
        "input_file_checksums": input_checksums,
        "output_file_checksums": output_checksums,
        "source_row_counts": {
            dataset: result.source_count for dataset, result in dataset_results.items()
        },
        "accepted_row_counts": {
            dataset: result.accepted_count for dataset, result in dataset_results.items()
        },
        "quarantined_row_counts": {
            dataset: result.quarantined_count for dataset, result in dataset_results.items()
        },
        "pipeline_status": status,
        "configuration_fingerprint": record_fingerprint(
            {
                "schema_policy": config.schema_policy,
                "duplicate_policy": config.duplicate_policy,
                "checksum_enforcement": config.checksum_enforcement,
            }
        ),
        "parent_source_manifest_checksum": source_manifest_checksum,
        "software_version": get_project_metadata().version,
    }
    path = output_dir / "ingestion-manifest.json"
    _atomic_write(path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return path


def write_lineage(output_dir: Path, dataset_results: dict[str, DatasetIngestionResult]) -> Path:
    """Write concise lineage relationships."""

    relationships = []
    for dataset in dataset_results:
        filename = CONTRACTS[dataset].filename
        relationships.append(
            {
                "dataset": dataset,
                "source": f"raw/{filename}",
                "validation": f"{dataset} contract validation",
                "accepted": f"accepted/{dataset}.jsonl",
                "quarantine": f"quarantine/{dataset}.jsonl",
            }
        )
    path = output_dir / "lineage.json"
    _atomic_write(
        path, json.dumps({"relationships": relationships}, indent=2, sort_keys=True) + "\n"
    )
    return path


def write_metrics(
    quality_dir: Path,
    *,
    files_discovered: int,
    dataset_results: dict[str, DatasetIngestionResult],
    stream_micro_batches: int = 0,
) -> Path:
    """Write structured run metrics."""

    metrics = {
        "files_discovered": files_discovered,
        "source_records_read": sum(result.source_count for result in dataset_results.values()),
        "records_accepted": sum(result.accepted_count for result in dataset_results.values()),
        "records_quarantined": sum(result.quarantined_count for result in dataset_results.values()),
        "parsing_failures": sum(
            1
            for result in dataset_results.values()
            for rule in result.rules
            if rule.rule_id in {"JSONL_MALFORMED", "JSONL_NON_OBJECT", "FIELD_TYPE_INVALID"}
        ),
        "validation_failures": sum(
            1 for result in dataset_results.values() for rule in result.rules if not rule.passed
        ),
        "duplicates_detected": sum(
            1
            for result in dataset_results.values()
            for rule in result.rules
            if rule.rule_id.startswith("DUPLICATE")
        ),
        "schema_drift_findings": sum(
            len(result.schema_drift) for result in dataset_results.values()
        ),
        "processing_duration_seconds": 0,
        "records_processed_per_second": None,
        "streaming_micro_batches_processed": stream_micro_batches,
    }
    path = quality_dir / "run-metrics.json"
    _atomic_write(path, json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    return path


def make_pipeline_result(
    *,
    run_id: str,
    status: str,
    output_dir: Path,
    quality_dir: Path,
    dataset_results: dict[str, DatasetIngestionResult],
    manifest_path: Path | None,
    quality_report_json_path: Path | None,
    quality_report_md_path: Path | None,
    lineage_path: Path | None,
    metrics_path: Path | None,
) -> PipelineResult:
    """Create a typed pipeline result."""

    return PipelineResult(
        run_id=run_id,
        status=status,  # type: ignore[arg-type]
        output_dir=output_dir,
        quality_dir=quality_dir,
        dataset_results=dataset_results,
        manifest_path=manifest_path,
        quality_report_json_path=quality_report_json_path,
        quality_report_md_path=quality_report_md_path,
        lineage_path=lineage_path,
        metrics_path=metrics_path,
    )


def _quality_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Ingestion Quality Report: {report['run_id']}",
        "",
        f"Overall status: **{report['overall_status']}**",
        "",
        "## Summary",
    ]
    summary = report["summary"]
    for key in (
        "source_records",
        "accepted_records",
        "quarantined_records",
        "warning_count",
        "error_count",
        "critical_count",
    ):
        lines.append(f"- {key}: {summary[key]}")
    lines.extend(
        [
            "",
            "## Dataset Scorecard",
            "",
            "| Dataset | Source | Accepted | Quarantine | Pass rate |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for dataset, details in report["datasets"].items():
        lines.append(
            "| {dataset} | {source} | {accepted} | {quarantine} | {rate} |".format(
                dataset=dataset,
                source=details["source_records"],
                accepted=details["accepted_records"],
                quarantine=details["quarantined_records"],
                rate=details["pass_rate"],
            )
        )
    lines.extend(["", "## Remediation", "", str(report["remediation"]), ""])
    return "\n".join(lines)


def _write_jsonl(path: Path, records: list[Record]) -> None:
    with NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", delete=False, dir=path.parent
    ) as handle:
        for record in records:
            handle.write(json.dumps(record, default=str, sort_keys=True, separators=(",", ":")))
            handle.write("\n")
        temporary_path = Path(handle.name)
    temporary_path.replace(path)


def _atomic_write(path: Path, content: str) -> None:
    with NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", delete=False, dir=path.parent
    ) as handle:
        handle.write(content)
        temporary_path = Path(handle.name)
    temporary_path.replace(path)
