import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from product_growth_intelligence.reporting import ReportingLayerConfig, run_reporting_layer
from product_growth_intelligence.reporting.dashboard_spec import (
    build_dashboard_pages,
    build_visual_specs,
)
from product_growth_intelligence.reporting.evidence_loader import load_reporting_evidence
from product_growth_intelligence.reporting.metric_dictionary import METRIC_DICTIONARY
from product_growth_intelligence.reporting.semantic_model import build_semantic_model
from product_growth_intelligence.reporting.tables import build_reporting_tables
from product_growth_intelligence.reporting.validation import validate_reporting_layer

FIXED_RUN_TIME = "2026-01-02T00:00:00Z"


def test_reporting_evidence_loading_and_tables_are_valid():
    evidence = load_reporting_evidence(Path("docs/evidence"))
    tables = build_reporting_tables(evidence)

    assert len(evidence) == 21
    assert set(tables) >= {
        "fact_product_health",
        "fact_funnel_performance",
        "fact_retention",
        "fact_churn_model_performance",
        "fact_segment_profiles",
        "fact_recommendation_performance",
        "fact_experiment_decisions",
        "fact_product_insights",
        "dim_metric",
        "dim_milestone",
        "dim_analysis_domain",
        "dim_date",
    }
    assert all(row["synthetic_data_flag"] is True for row in tables["fact_product_health"])


def test_missing_and_malformed_reporting_evidence_fail(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_reporting_evidence(tmp_path / "missing")

    evidence_root = tmp_path / "evidence"
    shutil.copytree("docs/evidence", evidence_root)
    (evidence_root / "milestone-8" / "model-comparison.csv").write_text(
        '"unterminated',
        encoding="utf-8",
    )
    evidence = load_reporting_evidence(evidence_root)
    with pytest.raises(ValueError, match="selected model"):
        build_reporting_tables(evidence)


def test_semantic_model_relationships_metrics_and_visuals_validate():
    evidence = load_reporting_evidence(Path("docs/evidence"))
    tables = build_reporting_tables(evidence)
    semantic_model = build_semantic_model(tables)
    pages = build_dashboard_pages()
    visuals = build_visual_specs()
    diagnostics = validate_reporting_layer(evidence, tables, semantic_model, pages, visuals)

    metric_ids = [str(row["metric_id"]) for row in METRIC_DICTIONARY]
    assert diagnostics["overall_status"] == "passed"
    assert len(metric_ids) == len(set(metric_ids))
    assert len(pages) == 8
    assert any(measure["metric_id"] == "churn_precision" for measure in semantic_model["measures"])
    assert all(visual["source_table"] in tables for visual in visuals)
    assert any("Guardrail Failure Count" in visual["measures"] for visual in visuals)


def test_reporting_outputs_manifest_lineage_and_overwrite_refusal(tmp_path: Path):
    config = _config(tmp_path, "sample")

    result = run_reporting_layer(config)

    assert result.status == "passed"
    assert result.table_count == 12
    output_dir = tmp_path / "reporting" / "sample"
    manifest = json.loads((output_dir / "reporting-manifest.json").read_text(encoding="utf-8"))
    lineage = json.loads((output_dir / "reporting-lineage.json").read_text(encoding="utf-8"))
    semantic_model = json.loads((output_dir / "semantic-model.json").read_text(encoding="utf-8"))
    assert "fact_product_health.csv" in manifest["output_checksums"]
    assert manifest["deployment_performed"] is False
    assert lineage["synthetic_data_flag"] is True
    assert semantic_model["data_sensitivity"] == "synthetic_non_customer_data"
    assert (output_dir / "powerbi-governance-notes.md").exists()
    with pytest.raises(FileExistsError):
        run_reporting_layer(config)


def test_reporting_validate_only_and_cli_success(tmp_path: Path):
    result = run_reporting_layer(
        ReportingLayerConfig(
            evidence_root=Path("docs/evidence"),
            output_root=tmp_path / "reporting",
            run_id="validate",
            fixed_run_time=FIXED_RUN_TIME,
            validate_only=True,
        )
    )

    assert result.status == "passed"
    assert not (tmp_path / "reporting" / "validate").exists()

    command = [
        sys.executable,
        "-m",
        "product_growth_intelligence",
        "build-reporting-layer",
        "--evidence-root",
        "docs/evidence",
        "--output-root",
        str(tmp_path / "cli-reporting"),
        "--run-id",
        "cli",
        "--fixed-run-time",
        FIXED_RUN_TIME,
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)

    assert completed.returncode == 0
    assert "status: passed" in completed.stdout
    assert "tables: 12" in completed.stdout


def test_reporting_cli_failure_for_missing_evidence(tmp_path: Path):
    command = [
        sys.executable,
        "-m",
        "product_growth_intelligence",
        "build-reporting-layer",
        "--evidence-root",
        str(tmp_path / "missing"),
        "--output-root",
        str(tmp_path / "reporting"),
        "--run-id",
        "failure",
    ]

    completed = subprocess.run(command, check=False, capture_output=True, text=True)

    assert completed.returncode != 0
    assert "Missing evidence directory" in completed.stderr


def test_reporting_evidence_generation_is_deterministic():
    completed = subprocess.run(
        [sys.executable, "scripts/generate_reporting_evidence.py"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert Path("docs/evidence/milestone-11/reporting-manifest.json").exists()


def _config(tmp_path: Path, run_id: str) -> ReportingLayerConfig:
    return ReportingLayerConfig(
        evidence_root=Path("docs/evidence"),
        output_root=tmp_path / "reporting",
        run_id=run_id,
        fixed_run_time=FIXED_RUN_TIME,
    )
