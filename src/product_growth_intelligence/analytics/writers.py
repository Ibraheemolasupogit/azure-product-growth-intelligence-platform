"""Output writers for funnel analytics."""

from __future__ import annotations

import csv
import json
from collections.abc import Callable
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from product_growth_intelligence.analytics.funnel_models import (
    FunnelAnalysisConfig,
    FunnelAttempt,
    FunnelDefinition,
    TrustedInput,
)
from product_growth_intelligence.analytics.inputs import (
    dataset_row_counts,
    source_manifest_checksum,
)
from product_growth_intelligence.data_generation.models import Record
from product_growth_intelligence.ingestion.fingerprints import file_sha256, record_fingerprint
from product_growth_intelligence.metadata import get_project_metadata


def prepare_analysis_output_dir(config: FunnelAnalysisConfig, run_id: str) -> Path:
    """Create or refuse the analysis output directory."""

    output_dir = config.output_root / run_id
    if output_dir.exists() and any(output_dir.iterdir()) and not config.overwrite:
        msg = f"Output directory {output_dir} already exists and is not empty. Pass --overwrite."
        raise FileExistsError(msg)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def write_analysis_outputs(
    output_dir: Path,
    *,
    config: FunnelAnalysisConfig,
    run_id: str,
    trusted: TrustedInput,
    definitions: tuple[FunnelDefinition, ...],
    attempts: list[FunnelAttempt],
    summary_rows: list[Record],
    stage_rows: list[Record],
    segment_rows: list[Record],
    time_rows: list[Record],
    dropoff_rows: list[Record],
    diagnostics: dict[str, Any],
) -> dict[str, str]:
    """Write all runtime analysis outputs except the final manifest."""

    checksums: dict[str, str] = {}
    files: dict[str, Callable[[Path], None]] = {
        "funnel-definitions.json": lambda path: _write_json(
            path, [_definition_record(definition) for definition in definitions]
        ),
        "funnel-attempts.jsonl": lambda path: _write_jsonl(
            path, [attempt.to_record() for attempt in attempts]
        ),
        "funnel-summary.csv": lambda path: _write_csv(path, summary_rows),
        "funnel-stage-metrics.csv": lambda path: _write_csv(path, stage_rows),
        "funnel-segment-metrics.csv": lambda path: _write_csv(path, segment_rows),
        "funnel-time-metrics.csv": lambda path: _write_csv(path, time_rows),
        "funnel-dropoff-analysis.csv": lambda path: _write_csv(path, dropoff_rows),
        "funnel-diagnostics.json": lambda path: _write_json(path, diagnostics),
        "analysis-lineage.json": lambda path: _write_json(
            path, _lineage_payload(trusted, definitions)
        ),
        "executive-funnel-report.md": lambda path: _write_text(
            path, executive_report(summary_rows, stage_rows, dropoff_rows, diagnostics)
        ),
    }
    for filename, writer in files.items():
        path = output_dir / filename
        writer(path)
        checksums[filename] = file_sha256(path)
    manifest_path = output_dir / "analysis-manifest.json"
    _write_json(
        manifest_path,
        _manifest_payload(
            config=config,
            run_id=run_id,
            trusted=trusted,
            definitions=definitions,
            output_checksums=checksums,
            output_rows={
                "funnel-attempts.jsonl": len(attempts),
                "funnel-summary.csv": len(summary_rows),
                "funnel-stage-metrics.csv": len(stage_rows),
                "funnel-segment-metrics.csv": len(segment_rows),
                "funnel-time-metrics.csv": len(time_rows),
                "funnel-dropoff-analysis.csv": len(dropoff_rows),
            },
            status=str(diagnostics["overall_status"]),
        ),
    )
    checksums["analysis-manifest.json"] = file_sha256(manifest_path)
    return checksums


def executive_report(
    summary_rows: list[Record],
    stage_rows: list[Record],
    dropoff_rows: list[Record],
    diagnostics: dict[str, Any],
) -> str:
    """Create a deterministic Markdown executive funnel report."""

    lines = [
        "# Executive Funnel Report",
        "",
        "Scope: governed funnel analytics over trusted Milestone 3 accepted datasets.",
        "",
        (
            "All data is synthetic. Findings are descriptive, associations are not causal, "
            "and small-sample evidence is illustrative."
        ),
        "",
        "## Major Funnel Results",
    ]
    for row in sorted(summary_rows, key=lambda item: str(item["funnel_id"])):
        result_line = (
            "- {funnel}: {completed}/{eligible} eligible users completed; "
            "entry rate {entry}; status {status}."
        )
        lines.append(
            result_line.format(
                funnel=row["funnel_id"],
                completed=row["completed"],
                eligible=row["eligible_users"],
                entry=row["entry_rate"],
                status=row["status"],
            )
        )
    lines.extend(["", "## Largest Stage Drop-Offs"])
    largest = sorted(
        stage_rows,
        key=lambda row: (int(row["drop_off_count"]), str(row["funnel_id"])),
        reverse=True,
    )[:5]
    for row in largest:
        lines.append(
            "- {funnel} / {stage}: {count} users dropped before reaching this stage.".format(
                funnel=row["funnel_id"], stage=row["stage_id"], count=row["drop_off_count"]
            )
        )
    lines.extend(["", "## Drop-Off Diagnostics"])
    for row in sorted(dropoff_rows, key=lambda item: str(item["funnel_id"]))[:8]:
        dropoff_line = (
            "- {funnel}: {count} attempts stopped after {stage}; next expected {next_stage}."
        )
        lines.append(
            dropoff_line.format(
                funnel=row["funnel_id"],
                count=row["drop_off_count"],
                stage=row["highest_stage_reached"],
                next_stage=row["next_expected_stage"],
            )
        )
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            (
                "- Experiment variants are descriptive slices only; no significance or "
                "uplift is calculated."
            ),
            (
                "- Funnel outputs do not implement retention, churn, segmentation models, "
                "recommendations, GenAI, or Power BI."
            ),
            f"- Diagnostics status: {diagnostics['overall_status']}.",
            "",
        ]
    )
    return "\n".join(lines)


def _manifest_payload(
    *,
    config: FunnelAnalysisConfig,
    run_id: str,
    trusted: TrustedInput,
    definitions: tuple[FunnelDefinition, ...],
    output_checksums: dict[str, str],
    output_rows: dict[str, int],
    status: str,
) -> dict[str, Any]:
    return {
        "analysis_run_id": run_id,
        "software_version": get_project_metadata().version,
        "source_ingestion_run_id": trusted.source_ingestion_run_id,
        "source_ingestion_manifest_checksum": source_manifest_checksum(trusted.input_dir),
        "source_contract_versions": trusted.contract_versions,
        "funnel_definition_versions": {
            definition.funnel_id: definition.version for definition in definitions
        },
        "configuration_fingerprint": record_fingerprint(
            {
                "analysis_start": config.analysis_start,
                "analysis_end": config.analysis_end,
                "attempt_policy": config.attempt_policy,
                "sequence_policy": config.sequence_policy,
                "suppression_threshold": config.suppression_threshold,
            }
        ),
        "analysis_period": {"start": config.analysis_start, "end": config.analysis_end},
        "attempt_policy": config.attempt_policy,
        "sequence_policy": config.sequence_policy,
        "censoring_policy": "right censor attempts whose completion window exceeds analysis_end",
        "suppression_threshold": config.suppression_threshold,
        "input_row_counts": dataset_row_counts(trusted),
        "output_row_counts": output_rows,
        "output_file_checksums": output_checksums,
        "overall_status": status,
        "created_at": config.fixed_analysis_time,
    }


def _lineage_payload(
    trusted: TrustedInput, definitions: tuple[FunnelDefinition, ...]
) -> dict[str, Any]:
    return {
        "source_ingestion_run_id": trusted.source_ingestion_run_id,
        "source_manifest_checksum": trusted.source_manifest_checksum,
        "source_contract_versions": trusted.contract_versions,
        "relationships": [
            "accepted/users",
            "accepted/sessions",
            "accepted/clickstream_events",
            "accepted/subscriptions",
            "accepted/experiment_assignments",
            "accepted/feature_usage",
            "journey reconstruction",
            "funnel attempts",
            "stage metrics",
            "segment metrics",
            "drop-off diagnostics",
        ],
        "funnels": [definition.funnel_id for definition in definitions],
    }


def _definition_record(definition: FunnelDefinition) -> Record:
    return {
        "funnel_id": definition.funnel_id,
        "funnel_name": definition.funnel_name,
        "version": definition.version,
        "business_objective": definition.business_objective,
        "analytical_entity": definition.analytical_entity,
        "allowed_completion_days": definition.allowed_completion_days,
        "eligibility_rule": definition.eligibility_rule,
        "conversion_outcome": definition.conversion_outcome,
        "supported_segments": list(definition.supported_segments),
        "product_owner": definition.product_owner,
        "metric_notes": definition.metric_notes,
        "stages": [
            {
                "stage_id": stage.stage_id,
                "stage_name": stage.stage_name,
                "event_names": list(stage.event_names),
                "minimum_event_count": stage.minimum_event_count,
                "subscription_paid_outcome": stage.subscription_paid_outcome,
            }
            for stage in definition.stages
        ],
    }


def _write_csv(path: Path, rows: list[Record]) -> None:
    fieldnames = tuple(rows[0]) if rows else ("empty",)
    with NamedTemporaryFile(
        "w", encoding="utf-8", newline="", delete=False, dir=path.parent
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field)) for field in fieldnames})
        temporary_path = Path(handle.name)
    temporary_path.replace(path)


def _write_json(path: Path, payload: object) -> None:
    _write_text(path, json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


def _write_jsonl(path: Path, rows: list[Record]) -> None:
    with NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", delete=False, dir=path.parent
    ) as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":"), default=str))
            handle.write("\n")
        temporary_path = Path(handle.name)
    temporary_path.replace(path)


def _write_text(path: Path, text: str) -> None:
    with NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", delete=False, dir=path.parent
    ) as handle:
        handle.write(text)
        temporary_path = Path(handle.name)
    temporary_path.replace(path)


def _csv_value(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return value
