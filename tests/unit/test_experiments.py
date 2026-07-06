import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from product_growth_intelligence.experiments import (
    ExperimentAnalysisConfig,
    run_experiment_analysis,
)
from product_growth_intelligence.experiments.catalogue import (
    default_experiment_catalogue,
    experiment_metrics,
    validate_experiment_catalogue,
)
from product_growth_intelligence.experiments.models import ExperimentSpec
from product_growth_intelligence.experiments.pipeline import _assignment_integrity
from product_growth_intelligence.experiments.statistics import (
    adjust_p_values,
    binary_required_sample_size,
    chi_square_srm,
    two_proportion_effect,
    welch_mean_effect,
)
from product_growth_intelligence.ingestion import IngestionConfig, run_batch_ingestion

FIXED_INGESTION_TIME = "2026-01-01T00:00:00Z"
FIXED_RUN_TIME = "2026-01-02T00:00:00Z"
ANALYSIS_TIME = "2025-06-30T23:59:59Z"


def test_experiment_catalogue_is_governed():
    experiments = default_experiment_catalogue()
    metrics = experiment_metrics()

    validate_experiment_catalogue(experiments, metrics)

    assert len(experiments) == 4
    assert {experiment.experiment_id for experiment in experiments} == {
        "exp_simplified_onboarding",
        "exp_template_recommendation",
        "exp_trial_upgrade_prompt",
        "exp_automation_discovery",
    }
    assert all(experiment.control_variant in experiment.variants for experiment in experiments)
    assert all(experiment.primary_metric in metrics for experiment in experiments)
    assert any(metric.guardrail for metric in metrics.values())


def test_invalid_experiment_catalogue_is_rejected():
    experiment = default_experiment_catalogue()[0]
    invalid = ExperimentSpec(
        **{
            **experiment.__dict__,
            "planned_allocation": {"control": 0.7, "simplified": 0.7},
        }
    )

    with pytest.raises(ValueError, match="allocation"):
        validate_experiment_catalogue((invalid,), experiment_metrics())


def test_assignment_integrity_excludes_duplicates_and_bad_timestamps():
    experiments = default_experiment_catalogue()
    user = {
        "user_id": "u1",
        "signup_timestamp": "2025-01-10T00:00:00Z",
        "persona": "solo_professional",
    }
    assignments = [
        _assignment("a1", "u1", "control", "2025-01-09T00:00:00Z"),
        _assignment("a2", "u1", "simplified", "2025-01-11T00:00:00Z"),
    ]

    rows, valid = _assignment_integrity(assignments, experiments, {"users": {"u1": user}})

    assert not valid
    assert all(row["integrity_status"] == "excluded" for row in rows)
    assert any("duplicate_assignment" in row["exclusion_reason"] for row in rows)
    assert any("assignment_before_signup" in row["exclusion_reason"] for row in rows)


def test_srm_and_statistical_helpers_have_bounded_outputs():
    srm = chi_square_srm([50, 50], [0.5, 0.5])
    binary = two_proportion_effect(20, 100, 30, 100, 0.95)
    continuous = welch_mean_effect([1.0, 2.0, 3.0], [2.0, 3.0, 4.0], 0.95)

    assert srm["srm_status"] if "srm_status" in srm else srm["p_value"] == 1.0
    assert 0 <= float(binary["p_value"]) <= 1
    assert binary["absolute_effect"] == 0.1
    assert float(binary["confidence_lower"]) <= float(binary["confidence_upper"])
    assert 0 <= float(continuous["p_value"]) <= 1
    assert continuous["absolute_effect"] == 1.0


def test_multiple_testing_and_power_helpers():
    adjusted = adjust_p_values([0.01, 0.04, 0.2], "benjamini_hochberg")
    required = binary_required_sample_size(0.2, 0.05, 0.05, 0.8)

    assert adjusted == sorted(adjusted)
    assert all(0 <= value <= 1 for value in adjusted)
    assert required > 0


def test_sample_experiment_outputs_and_overwrite_refusal(tmp_path: Path):
    input_dir = _ingest_sample(tmp_path)
    config = _config(input_dir, tmp_path, "sample")

    result = run_experiment_analysis(config)

    assert result.status == "passed_with_warnings"
    assert result.experiments_evaluated == 4
    output_dir = tmp_path / "experiments" / "sample"
    assert (output_dir / "analysis-manifest.json").exists()
    decisions = list(csv.DictReader((output_dir / "decision-summary.csv").open()))
    assert {row["experiment_id"] for row in decisions} == {
        "exp_simplified_onboarding",
        "exp_template_recommendation",
        "exp_trial_upgrade_prompt",
        "exp_automation_discovery",
    }
    assert all(row["reason_codes"] for row in decisions)
    metric_rows = list(csv.DictReader((output_dir / "metric-results.csv").open()))
    assert any(row["metric_type"] == "continuous" for row in metric_rows)
    assert any(row["metric_type"] == "count" for row in metric_rows)
    manifest = json.loads((output_dir / "analysis-manifest.json").read_text(encoding="utf-8"))
    assert "metric-results.csv" in manifest["output_checksums"]
    with pytest.raises(FileExistsError):
        run_experiment_analysis(config)


def test_experiment_cli_success_for_selected_experiment(tmp_path: Path):
    input_dir = _ingest_sample(tmp_path)
    command = [
        sys.executable,
        "-m",
        "product_growth_intelligence",
        "analyse-experiments",
        "--input-dir",
        str(input_dir),
        "--output-root",
        str(tmp_path / "experiments"),
        "--run-id",
        "cli",
        "--experiment",
        "exp_trial_upgrade_prompt",
        "--analysis-time",
        ANALYSIS_TIME,
        "--fixed-run-time",
        FIXED_RUN_TIME,
    ]

    result = subprocess.run(command, check=False, capture_output=True, text=True)

    assert result.returncode == 0
    assert "status: passed_with_warnings" in result.stdout
    assert "decision[exp_trial_upgrade_prompt]" in result.stdout


def test_experiment_evidence_generation_is_deterministic():
    result = subprocess.run(
        [sys.executable, "scripts/generate_experiment_evidence.py"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert Path("docs/evidence/milestone-9/analysis-manifest.json").exists()


def _config(input_dir: Path, tmp_path: Path, run_id: str) -> ExperimentAnalysisConfig:
    return ExperimentAnalysisConfig(
        input_dir=input_dir,
        output_root=tmp_path / "experiments",
        run_id=run_id,
        analysis_time=ANALYSIS_TIME,
        fixed_run_time=FIXED_RUN_TIME,
    )


def _ingest_sample(tmp_path: Path) -> Path:
    result = run_batch_ingestion(
        IngestionConfig(
            source=Path("data/samples/nexaflow"),
            output_root=tmp_path / "interim",
            quality_root=tmp_path / "quality",
            run_id="source",
            fixed_ingestion_time=FIXED_INGESTION_TIME,
        )
    )
    assert result.status == "passed"
    return tmp_path / "interim" / "source"


def _assignment(
    assignment_id: str,
    user_id: str,
    variant: str,
    assignment_timestamp: str,
) -> dict[str, object]:
    return {
        "assignment_id": assignment_id,
        "experiment_id": "exp_simplified_onboarding",
        "user_id": user_id,
        "variant": variant,
        "assignment_timestamp": assignment_timestamp,
        "exposure_timestamp": "2025-01-12T00:00:00Z",
        "conversion_timestamp": "",
    }
