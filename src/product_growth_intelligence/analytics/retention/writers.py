"""Writers for retention analytics outputs."""

from __future__ import annotations

import csv
import json
from collections.abc import Callable
from pathlib import Path
from tempfile import NamedTemporaryFile

from product_growth_intelligence.analytics.funnel_models import TrustedInput
from product_growth_intelligence.analytics.inputs import (
    dataset_row_counts,
    source_manifest_checksum,
)
from product_growth_intelligence.analytics.retention.models import (
    CohortMembership,
    RetentionAnalysisConfig,
    RetentionDefinition,
    UserPeriodActivity,
)
from product_growth_intelligence.data_generation.models import Record
from product_growth_intelligence.ingestion.fingerprints import file_sha256, record_fingerprint
from product_growth_intelligence.metadata import get_project_metadata


def prepare_output_dir(config: RetentionAnalysisConfig, run_id: str) -> Path:
    """Create or refuse the output directory."""

    output_dir = config.output_root / run_id
    if output_dir.exists() and any(output_dir.iterdir()) and not config.overwrite:
        msg = f"Output directory {output_dir} already exists and is not empty. Pass --overwrite."
        raise FileExistsError(msg)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def write_outputs(
    output_dir: Path,
    *,
    config: RetentionAnalysisConfig,
    run_id: str,
    trusted: TrustedInput,
    definitions: tuple[RetentionDefinition, ...],
    memberships: list[CohortMembership],
    user_periods: list[UserPeriodActivity],
    matrix_rows: list[Record],
    long_rows: list[Record],
    cohort_summary_rows: list[Record],
    segment_rows: list[Record],
    lifecycle_rows: list[Record],
    resurrection_rows: list[Record],
    diagnostics: dict[str, object],
) -> dict[str, str]:
    """Write runtime outputs and the manifest last."""

    checksums: dict[str, str] = {}
    files: dict[str, Callable[[Path], None]] = {
        "retention-definitions.json": lambda path: _write_json(
            path, [_definition_record(definition) for definition in definitions]
        ),
        "cohort-memberships.jsonl": lambda path: _write_jsonl(
            path, [membership.to_record() for membership in memberships]
        ),
        "user-period-activity.jsonl": lambda path: _write_jsonl(
            path, [period.to_record() for period in user_periods]
        ),
        "retention-matrix.csv": lambda path: _write_csv(path, matrix_rows),
        "retention-long.csv": lambda path: _write_csv(path, long_rows),
        "rolling-retention.csv": lambda path: _write_csv(path, long_rows),
        "cohort-summary.csv": lambda path: _write_csv(path, cohort_summary_rows),
        "segment-retention.csv": lambda path: _write_csv(path, segment_rows),
        "lifecycle-status.csv": lambda path: _write_csv(path, lifecycle_rows),
        "resurrection-analysis.csv": lambda path: _write_csv(path, resurrection_rows),
        "retention-diagnostics.json": lambda path: _write_json(path, diagnostics),
        "analysis-lineage.json": lambda path: _write_json(path, _lineage(trusted, definitions)),
        "executive-retention-report.md": lambda path: _write_text(
            path, executive_report(definitions, long_rows, cohort_summary_rows, diagnostics)
        ),
    }
    for filename, writer in files.items():
        path = output_dir / filename
        writer(path)
        checksums[filename] = file_sha256(path)
    manifest_path = output_dir / "analysis-manifest.json"
    _write_json(
        manifest_path,
        _manifest(
            config=config,
            run_id=run_id,
            trusted=trusted,
            definitions=definitions,
            output_checksums=checksums,
            output_rows={
                "cohort-memberships.jsonl": len(memberships),
                "user-period-activity.jsonl": len(user_periods),
                "retention-matrix.csv": len(matrix_rows),
                "retention-long.csv": len(long_rows),
                "cohort-summary.csv": len(cohort_summary_rows),
                "segment-retention.csv": len(segment_rows),
                "lifecycle-status.csv": len(lifecycle_rows),
                "resurrection-analysis.csv": len(resurrection_rows),
            },
            status=str(diagnostics["overall_status"]),
        ),
    )
    checksums["analysis-manifest.json"] = file_sha256(manifest_path)
    return checksums


def executive_report(
    definitions: tuple[RetentionDefinition, ...],
    long_rows: list[Record],
    cohort_summary_rows: list[Record],
    diagnostics: dict[str, object],
) -> str:
    """Create deterministic Markdown report."""

    strongest = sorted(
        [
            row
            for row in long_rows
            if row["period_index"] == 1 and row["suppression_status"] == "shown"
        ],
        key=lambda row: (float(row["classic_retention_rate"] or 0), str(row["definition_id"])),
        reverse=True,
    )[:3]
    weakest = sorted(
        [
            row
            for row in long_rows
            if row["period_index"] == 1 and row["suppression_status"] == "shown"
        ],
        key=lambda row: (float(row["classic_retention_rate"] or 0), str(row["definition_id"])),
    )[:3]
    lines = [
        "# Executive Retention Report",
        "",
        "Scope: governed weekly retention over trusted Milestone 3 accepted datasets.",
        "",
        (
            "All data is synthetic. Findings are descriptive, associations are not causal, "
            "and small-sample evidence is illustrative. Censored recent cohorts should not "
            "be interpreted as failed retention."
        ),
        "",
        "## Definitions Used",
    ]
    lines.extend(f"- {definition.definition_id}" for definition in definitions)
    lines.extend(["", "## Strongest Observed Period-1 Cohorts"])
    lines.extend(_cohort_lines(strongest))
    lines.extend(["", "## Weakest Observed Period-1 Cohorts"])
    lines.extend(_cohort_lines(weakest))
    lines.extend(["", "## Resurrection Findings"])
    resurrected = sum(int(row["resurrected_users"]) for row in cohort_summary_rows)
    lines.append(f"- Resurrected user-period patterns observed: {resurrected}.")
    lines.extend(
        [
            "",
            "## Recommended Investigation Areas",
            "",
            "- Compare activated versus non-activated retention in larger samples.",
            "- Inspect paid and collaboration cohorts as observation windows mature.",
            "- Treat resurrection and churn-like inactivity as descriptive lifecycle states only.",
            f"- Diagnostics status: {diagnostics['overall_status']}.",
            "",
        ]
    )
    return "\n".join(lines)


def _cohort_lines(rows: list[Record]) -> list[str]:
    if not rows:
        return ["- No unsuppressed period-1 cohorts available."]
    return [
        "- {definition} {cohort}: period-1 classic retention {rate}.".format(
            definition=row["definition_id"],
            cohort=row["cohort_period"],
            rate=row["classic_retention_rate"],
        )
        for row in rows
    ]


def _manifest(
    *,
    config: RetentionAnalysisConfig,
    run_id: str,
    trusted: TrustedInput,
    definitions: tuple[RetentionDefinition, ...],
    output_checksums: dict[str, str],
    output_rows: dict[str, int],
    status: str,
) -> dict[str, object]:
    return {
        "analysis_run_id": run_id,
        "software_version": get_project_metadata().version,
        "source_ingestion_run_id": trusted.source_ingestion_run_id,
        "source_manifest_checksum": source_manifest_checksum(trusted.input_dir),
        "source_contract_versions": trusted.contract_versions,
        "retention_definition_versions": {
            definition.definition_id: definition.version for definition in definitions
        },
        "analysis_configuration_fingerprint": record_fingerprint(
            {
                "analysis_start": config.analysis_start,
                "analysis_end": config.analysis_end,
                "time_grain": config.time_grain,
                "horizon": config.horizon,
                "suppression_threshold": config.suppression_threshold,
            }
        ),
        "analysis_start": config.analysis_start,
        "analysis_end": config.analysis_end,
        "time_grain": config.time_grain,
        "horizon": config.horizon,
        "activity_definition": (
            "qualifying product events excluding session_started, errors, "
            "and passive recommendation exposure"
        ),
        "censoring_policy": "periods whose full interval has not elapsed are censored",
        "suppression_threshold": config.suppression_threshold,
        "input_row_counts": dataset_row_counts(trusted),
        "output_row_counts": output_rows,
        "output_checksums": output_checksums,
        "overall_status": status,
        "created_at": config.fixed_analysis_time,
    }


def _lineage(
    trusted: TrustedInput, definitions: tuple[RetentionDefinition, ...]
) -> dict[str, object]:
    return {
        "source_ingestion_run_id": trusted.source_ingestion_run_id,
        "source_manifest_checksum": trusted.source_manifest_checksum,
        "source_contract_versions": trusted.contract_versions,
        "relationships": [
            "accepted/users",
            "accepted/sessions",
            "accepted/clickstream_events",
            "accepted/subscriptions",
            "accepted/feature_usage",
            "activity normalisation",
            "cohort assignment",
            "period observation",
            "retention metrics",
            "lifecycle and resurrection outputs",
        ],
        "definitions": [definition.definition_id for definition in definitions],
    }


def _definition_record(definition: RetentionDefinition) -> Record:
    return {
        "definition_id": definition.definition_id,
        "name": definition.name,
        "version": definition.version,
        "business_objective": definition.business_objective,
        "anchor_rule": definition.anchor_rule,
        "eligibility_rule": definition.eligibility_rule,
        "activity_events": list(definition.activity_rule.event_names),
        "time_grain": definition.time_grain,
        "maximum_horizon": definition.maximum_horizon,
        "inactivity_threshold_periods": definition.inactivity_threshold_periods,
        "churn_threshold_periods": definition.churn_threshold_periods,
        "resurrection_rule": definition.resurrection_rule,
        "supported_segments": list(definition.supported_segments),
        "metric_notes": definition.metric_notes,
        "owner": definition.owner,
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
