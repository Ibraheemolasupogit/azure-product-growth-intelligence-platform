"""Manifest and lineage helpers for reporting outputs."""

from __future__ import annotations

from pathlib import Path

from product_growth_intelligence.ingestion.fingerprints import file_sha256
from product_growth_intelligence.reporting.evidence_loader import EvidenceArtifact


def build_manifest(
    output_dir: Path,
    run_id: str,
    run_time: str,
    diagnostics: dict[str, object],
) -> dict[str, object]:
    """Build a deterministic reporting manifest."""

    checksums = {
        path.name: file_sha256(path)
        for path in sorted(output_dir.iterdir())
        if path.is_file() and path.name != "reporting-manifest.json"
    }
    return {
        "reporting_layer_version": "2026-07-milestone-11",
        "run_id": run_id,
        "run_time": run_time,
        "status": diagnostics["overall_status"],
        "output_checksums": checksums,
        "synthetic_data_flag": True,
        "deployment_performed": False,
        "powerbi_file_created": False,
    }


def build_lineage(evidence: dict[str, EvidenceArtifact], tables: list[str]) -> dict[str, object]:
    """Build lineage from prior milestone evidence to reporting outputs."""

    return {
        "reporting_layer_version": "2026-07-milestone-11",
        "source_artifacts": [
            {
                "artifact_id": key,
                "path": value["path"],
                "checksum": value["checksum"],
                "milestone": value["milestone"],
            }
            for key, value in sorted(evidence.items())
        ],
        "transformations": [
            "load committed evidence artifacts",
            "validate evidence availability and parseability",
            "build compact star-schema reporting tables",
            "build semantic model and metric dictionary",
            "build dashboard and visual specifications",
            "write manifest, diagnostics, and governance notes",
        ],
        "output_tables": sorted(tables),
        "azure_mapping": {
            "csv_outputs": "ADLS Gen2 curated reporting zone",
            "semantic_model_json": "Power BI semantic model / Tabular model design",
            "metric_dictionary": "Certified Power BI metrics / governance catalogue",
            "dashboard_specification": "Power BI report pages",
            "refresh_plan": "Power BI scheduled refresh / Data Factory orchestration",
            "lineage": "Microsoft Purview",
        },
        "synthetic_data_flag": True,
        "deployment_performed": False,
    }
