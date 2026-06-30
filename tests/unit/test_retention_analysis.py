import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from product_growth_intelligence.analytics.retention import (
    RetentionAnalysisConfig,
    run_retention_analysis,
)
from product_growth_intelligence.analytics.retention.definitions import (
    default_retention_definitions,
    validate_retention_definitions,
)
from product_growth_intelligence.analytics.retention.periods import (
    add_periods,
    parse_timestamp,
    period_index,
    period_label,
)
from product_growth_intelligence.ingestion import IngestionConfig, run_batch_ingestion

FIXED_INGESTION_TIME = "2026-01-01T00:00:00Z"
FIXED_ANALYSIS_TIME = "2026-01-02T00:00:00Z"


def test_retention_definitions_are_valid_and_unique():
    definitions = default_retention_definitions("weekly", 4)

    validate_retention_definitions(definitions)

    keys = {(definition.definition_id, definition.version) for definition in definitions}
    assert len(keys) == 6


def test_invalid_thresholds_are_rejected():
    definition = default_retention_definitions()[0]
    invalid = definition.__class__(**{**definition.__dict__, "churn_threshold_periods": 1})

    with pytest.raises(ValueError, match="Invalid churn threshold"):
        validate_retention_definitions((invalid,))


def test_period_indexing_daily_weekly_and_monthly():
    anchor = parse_timestamp("2025-01-31T12:00:00Z")
    later = parse_timestamp("2025-02-03T00:00:00Z")

    assert period_label(anchor, "weekly") == "2025-W05"
    assert period_index(anchor, later, "daily") == 3
    assert period_index(anchor, later, "weekly") == 1
    assert period_index(anchor, later, "monthly") == 1
    assert add_periods(parse_timestamp("2025-01-01T00:00:00Z"), 1, "monthly").month == 2


def test_weekly_sample_retention_outputs(tmp_path: Path):
    input_dir = _ingest_sample(tmp_path)
    result = run_retention_analysis(
        RetentionAnalysisConfig(
            input_dir=input_dir,
            output_root=tmp_path / "retention",
            run_id="weekly",
            time_grain="weekly",
            horizon=4,
            suppression_threshold=1,
            fixed_analysis_time=FIXED_ANALYSIS_TIME,
        )
    )

    assert result.status == "passed"
    assert result.memberships
    assert result.user_periods
    long_rows = list(
        csv.DictReader((tmp_path / "retention" / "weekly" / "retention-long.csv").open())
    )
    assert {"definition_id", "period_index", "classic_retention_rate"} <= set(long_rows[0])


def test_selected_definition_and_overwrite_refusal(tmp_path: Path):
    input_dir = _ingest_sample(tmp_path)
    config = RetentionAnalysisConfig(
        input_dir=input_dir,
        output_root=tmp_path / "retention",
        run_id="selected",
        enabled_definitions=("signup_retention",),
        horizon=2,
        suppression_threshold=1,
        fixed_analysis_time=FIXED_ANALYSIS_TIME,
    )

    first = run_retention_analysis(config)

    assert {membership.definition_id for membership in first.memberships} == {"signup_retention"}
    with pytest.raises(FileExistsError):
        run_retention_analysis(config)


def test_censored_recent_periods_are_not_zero_retention(tmp_path: Path):
    input_dir = _ingest_sample(tmp_path)
    result = run_retention_analysis(
        RetentionAnalysisConfig(
            input_dir=input_dir,
            output_root=tmp_path / "retention",
            run_id="censored",
            analysis_end="2025-02-01T00:00:00Z",
            horizon=6,
            suppression_threshold=1,
            fixed_analysis_time=FIXED_ANALYSIS_TIME,
        )
    )

    assert any(int(row["censored_users"]) > 0 for row in result.retention_long_rows)
    censored_rows = [
        row for row in result.retention_long_rows if int(row["observed_denominator"]) == 0
    ]
    assert all(row["classic_retention_rate"] is None for row in censored_rows)


def test_daily_and_monthly_smoke(tmp_path: Path):
    input_dir = _ingest_sample(tmp_path)
    for grain in ("daily", "monthly"):
        result = run_retention_analysis(
            RetentionAnalysisConfig(
                input_dir=input_dir,
                output_root=tmp_path / f"retention-{grain}",
                run_id=grain,
                time_grain=grain,  # type: ignore[arg-type]
                horizon=2,
                suppression_threshold=1,
                fixed_analysis_time=FIXED_ANALYSIS_TIME,
            )
        )
        assert result.status == "passed"


def test_incompatible_input_fails(tmp_path: Path):
    input_dir = _ingest_sample(tmp_path)
    manifest_path = input_dir / "ingestion-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["contract_versions"]["users"] = "old"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="incompatible contract"):
        run_retention_analysis(
            RetentionAnalysisConfig(input_dir=input_dir, output_root=tmp_path / "retention")
        )


def test_retention_cli_success(tmp_path: Path):
    input_dir = _ingest_sample(tmp_path)
    command = [
        sys.executable,
        "-m",
        "product_growth_intelligence",
        "analyse-retention",
        "--input-dir",
        str(input_dir),
        "--output-root",
        str(tmp_path / "retention"),
        "--run-id",
        "cli",
        "--definition",
        "signup_retention",
        "--horizon",
        "2",
        "--suppression-threshold",
        "1",
        "--fixed-analysis-time",
        FIXED_ANALYSIS_TIME,
    ]

    result = subprocess.run(command, check=False, capture_output=True, text=True)

    assert result.returncode == 0
    assert "status: passed" in result.stdout
    assert "memberships:" in result.stdout


def test_retention_evidence_generation_is_deterministic():
    result = subprocess.run(
        [sys.executable, "scripts/generate_retention_evidence.py"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert Path("docs/evidence/milestone-5/analysis-manifest.json").exists()


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
