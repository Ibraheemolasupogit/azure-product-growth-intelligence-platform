import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from product_growth_intelligence.analytics import FunnelAnalysisConfig, run_funnel_analysis
from product_growth_intelligence.analytics.funnel_definitions import (
    default_funnel_definitions,
    validate_funnel_definitions,
)
from product_growth_intelligence.analytics.funnel_models import TrustedInput
from product_growth_intelligence.analytics.journey import reconstruct_attempts
from product_growth_intelligence.ingestion import IngestionConfig, run_batch_ingestion

FIXED_INGESTION_TIME = "2026-01-01T00:00:00Z"
FIXED_ANALYSIS_TIME = "2026-01-02T00:00:00Z"


def test_default_funnel_definitions_are_valid_and_unique():
    definitions = default_funnel_definitions()

    validate_funnel_definitions(definitions)

    keys = {(definition.funnel_id, definition.version) for definition in definitions}
    assert len(keys) == 6


def test_invalid_funnel_definition_rejects_unknown_event():
    definition = default_funnel_definitions()[0]
    bad_stage = definition.stages[0].__class__("bad_stage", "Bad stage", ("not_a_real_event",))
    bad_definition = definition.__class__(
        **{**definition.__dict__, "stages": (bad_stage, *definition.stages[1:])}
    )

    with pytest.raises(ValueError, match="unknown events"):
        validate_funnel_definitions((bad_definition,))


def test_journey_reconstruction_handles_first_entry_and_completion():
    trusted = _trusted_input(
        events=[
            _event("u1", "s1", "e1", "recommendation_shown", "2025-01-01T00:00:00Z", 1),
            _event("u1", "s1", "e2", "recommendation_shown", "2025-01-01T00:01:00Z", 2),
            _event("u1", "s1", "e3", "recommendation_clicked", "2025-01-01T00:02:00Z", 3),
            _event("u1", "s1", "e4", "recommendation_accepted", "2025-01-01T00:03:00Z", 4),
        ]
    )
    definition = [
        item
        for item in default_funnel_definitions()
        if item.funnel_id == "recommendation_interaction"
    ][0]

    attempts, eligible, _ = reconstruct_attempts(
        trusted, (definition,), "2025-01-01T00:00:00Z", "2025-02-01T00:00:00Z"
    )

    assert eligible["recommendation_interaction"] == 1
    assert len(attempts) == 1
    assert attempts[0].attempt_status == "completed"
    assert attempts[0].entry_timestamp == "2025-01-01T00:00:00Z"


def test_subscription_confirmed_paid_conversion_and_censoring():
    trusted = _trusted_input(
        events=[
            _event("u1", "s1", "e1", "upgrade_prompt_viewed", "2025-01-01T00:00:00Z", 1),
            _event("u1", "s1", "e2", "trial_started", "2025-01-01T00:01:00Z", 2),
            _event("u1", "s1", "e3", "subscription_started", "2025-01-01T00:02:00Z", 3),
            _event("u2", "s2", "e4", "recommendation_shown", "2025-01-30T00:00:00Z", 1),
        ],
        users=[_user("u1"), _user("u2")],
        subscriptions=[
            {
                "subscription_id": "sub1",
                "user_id": "u1",
                "plan_name": "starter",
                "status": "active",
                "period_start_timestamp": "2025-01-01T00:03:00Z",
            }
        ],
    )
    definitions = {definition.funnel_id: definition for definition in default_funnel_definitions()}

    paid_attempts, _, _ = reconstruct_attempts(
        trusted, (definitions["trial_to_paid"],), "2025-01-01T00:00:00Z", "2025-03-01T00:00:00Z"
    )
    censored_attempts, _, _ = reconstruct_attempts(
        trusted,
        (definitions["recommendation_interaction"],),
        "2025-01-01T00:00:00Z",
        "2025-02-01T00:00:00Z",
    )

    assert paid_attempts[0].attempt_status == "completed"
    assert paid_attempts[0].stage_event_ids["paid_conversion"] == "subscription:sub1"
    assert censored_attempts[0].attempt_status == "censored"


def test_sample_funnel_analysis_outputs_and_manifest(tmp_path: Path):
    input_dir = _ingest_sample(tmp_path)
    result = run_funnel_analysis(
        FunnelAnalysisConfig(
            input_dir=input_dir,
            output_root=tmp_path / "funnels",
            run_id="sample",
            fixed_analysis_time=FIXED_ANALYSIS_TIME,
            suppression_threshold=1,
        )
    )

    assert result.status == "passed"
    assert len(result.summary_rows) == 6
    assert (tmp_path / "funnels" / "sample" / "analysis-manifest.json").exists()
    summary_rows = list(
        csv.DictReader((tmp_path / "funnels" / "sample" / "funnel-summary.csv").open())
    )
    recommendation = [
        row for row in summary_rows if row["funnel_id"] == "recommendation_interaction"
    ][0]
    assert recommendation["completed"] == "1"


def test_selected_funnel_analysis_and_overwrite_refusal(tmp_path: Path):
    input_dir = _ingest_sample(tmp_path)
    config = FunnelAnalysisConfig(
        input_dir=input_dir,
        output_root=tmp_path / "funnels",
        run_id="selected",
        enabled_funnels=("recommendation_interaction",),
        fixed_analysis_time=FIXED_ANALYSIS_TIME,
        suppression_threshold=1,
    )

    first = run_funnel_analysis(config)

    assert len(first.summary_rows) == 1
    with pytest.raises(FileExistsError):
        run_funnel_analysis(config)


def test_incompatible_input_fails_clearly(tmp_path: Path):
    input_dir = _ingest_sample(tmp_path)
    manifest_path = input_dir / "ingestion-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pipeline_status"] = "failed"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="passed Milestone 3"):
        run_funnel_analysis(
            FunnelAnalysisConfig(input_dir=input_dir, output_root=tmp_path / "funnels")
        )


def test_funnel_cli_success(tmp_path: Path):
    input_dir = _ingest_sample(tmp_path)
    command = [
        sys.executable,
        "-m",
        "product_growth_intelligence",
        "analyse-funnels",
        "--input-dir",
        str(input_dir),
        "--output-root",
        str(tmp_path / "funnels"),
        "--run-id",
        "cli",
        "--funnel",
        "recommendation_interaction",
        "--suppression-threshold",
        "1",
        "--fixed-analysis-time",
        FIXED_ANALYSIS_TIME,
    ]

    result = subprocess.run(command, check=False, capture_output=True, text=True)

    assert result.returncode == 0
    assert "status: passed" in result.stdout
    assert "completed: 1" in result.stdout


def test_funnel_evidence_generation_is_deterministic():
    result = subprocess.run(
        [sys.executable, "scripts/generate_funnel_evidence.py"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert Path("docs/evidence/milestone-4/analysis-manifest.json").exists()


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


def _trusted_input(
    events: list[dict[str, object]],
    users: list[dict[str, object]] | None = None,
    subscriptions: list[dict[str, object]] | None = None,
) -> TrustedInput:
    users = users or [_user("u1")]
    return TrustedInput(
        input_dir=Path("/tmp/test"),
        ingestion_manifest={"pipeline_status": "passed"},
        source_manifest_checksum="checksum",
        source_ingestion_run_id="source",
        contract_versions={},
        datasets={
            "users": users,
            "sessions": [
                {"session_id": "s1", "user_id": "u1", "device_type": "desktop"},
                {"session_id": "s2", "user_id": "u2", "device_type": "desktop"},
            ],
            "clickstream_events": events,
            "feature_usage": [],
            "subscriptions": subscriptions or [],
            "experiment_assignments": [],
        },
    )


def _user(user_id: str) -> dict[str, object]:
    return {
        "user_id": user_id,
        "signup_timestamp": "2025-01-01T00:00:00Z",
        "persona": "power_user",
        "acquisition_channel": "organic_search",
        "country": "Canada",
        "region": "North America",
        "device_preference": "desktop",
        "initial_plan": "free",
        "company_size_band": "2-10",
        "is_team_account": True,
    }


def _event(
    user_id: str,
    session_id: str,
    event_id: str,
    event_name: str,
    timestamp: str,
    sequence: int,
) -> dict[str, object]:
    return {
        "user_id": user_id,
        "session_id": session_id,
        "event_id": event_id,
        "event_name": event_name,
        "event_timestamp": timestamp,
        "event_sequence_number": sequence,
        "device_type": "desktop",
        "feature_name": None,
        "page_name": "workspace",
        "journey_stage": "engagement",
        "properties": {},
    }
