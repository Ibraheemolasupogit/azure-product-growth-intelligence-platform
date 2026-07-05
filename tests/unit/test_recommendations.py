import csv
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from product_growth_intelligence.ingestion import IngestionConfig, run_batch_ingestion
from product_growth_intelligence.models.recommendations import (
    RecommendationConfig,
    run_recommendations,
)
from product_growth_intelligence.models.recommendations.pipeline import (
    _build_inputs,
    interaction_mapping,
    item_catalogue,
)

FIXED_INGESTION_TIME = "2026-01-01T00:00:00Z"
FIXED_RUN_TIME = "2026-01-02T00:00:00Z"
SNAPSHOT_TIME = "2025-02-28T23:59:59Z"


def test_catalogue_and_interaction_mapping_are_governed():
    catalogue = item_catalogue()
    mapping = interaction_mapping()
    item_ids = {row["item_id"] for row in catalogue}

    assert len(catalogue) == 16
    assert len(item_ids) == len(catalogue)
    assert {"feature", "template", "automation", "integration"} <= {
        row["item_category"] for row in catalogue
    }
    assert {"recommendation_shown", "recommendation_clicked", "recommendation_accepted"} <= {
        row["event_name"] for row in mapping
    }
    assert all(row["item_id"] in item_ids | {"recommendation"} for row in mapping)
    assert {row["mapping_version"] for row in mapping} == {"2026-07-milestone-8-interactions"}


def test_invalid_recommendation_configuration_is_rejected():
    with pytest.raises(ValueError, match="lookback_days"):
        RecommendationConfig(
            input_dir=Path("unused"),
            output_root=Path("unused"),
            lookback_days=0,
        ).validate()

    with pytest.raises(ValueError, match="top_k"):
        RecommendationConfig(
            input_dir=Path("unused"),
            output_root=Path("unused"),
            top_k=(5, 5),
        ).validate()


def test_post_snapshot_events_do_not_change_training_interactions(tmp_path: Path):
    input_dir = _ingest_sample(tmp_path)
    config = _config(input_dir, tmp_path, "before")
    before, _, _, _, _ = _build_inputs(config)
    target_user = str(before[0]["user_id"])
    _append_event(input_dir, target_user, _parse_timestamp(SNAPSHOT_TIME) + timedelta(days=1))

    after, holdout, _, _, _ = _build_inputs(_config(input_dir, tmp_path, "after"))

    assert after == before
    assert "feature_task_management" in holdout[target_user]


def test_sample_recommendation_outputs_and_overwrite_refusal(tmp_path: Path):
    input_dir = _ingest_sample(tmp_path)
    config = _config(input_dir, tmp_path, "sample")

    result = run_recommendations(config)

    assert result.status == "passed"
    assert result.eligible_users == 12
    assert result.evaluated_users == 3
    assert result.selected_model == "segment_popularity"
    output_dir = tmp_path / "recommendations" / "sample"
    assert (output_dir / "recommendation-manifest.json").exists()
    recommendations = list(csv.DictReader((output_dir / "recommendations.csv").open()))
    assert recommendations
    assert all(int(row["rank"]) <= 10 for row in recommendations)
    selected = list(csv.DictReader((output_dir / "model-comparison.csv").open()))
    assert sum(1 for row in selected if row["selected_status"] == "selected") == 1
    candidates = [
        json.loads(line)
        for line in (output_dir / "candidate-items.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert all(row["eligibility_status"] == "eligible" for row in candidates)
    assert all(
        row["plan_name"] == "business" or not str(row["item_id"]).startswith("automation_")
        for row in candidates
    )
    with pytest.raises(FileExistsError):
        run_recommendations(config)


def test_recommendation_cli_success(tmp_path: Path):
    input_dir = _ingest_sample(tmp_path)
    command = [
        sys.executable,
        "-m",
        "product_growth_intelligence",
        "build-recommendations",
        "--input-dir",
        str(input_dir),
        "--output-root",
        str(tmp_path / "recommendations"),
        "--run-id",
        "cli",
        "--snapshot-time",
        SNAPSHOT_TIME,
        "--lookback-days",
        "56",
        "--holdout-days",
        "28",
        "--fixed-run-time",
        FIXED_RUN_TIME,
    ]

    result = subprocess.run(command, check=False, capture_output=True, text=True)

    assert result.returncode == 0
    assert "status: passed" in result.stdout
    assert "selected_model: segment_popularity" in result.stdout


def test_recommendation_evidence_generation_is_deterministic():
    result = subprocess.run(
        [sys.executable, "scripts/generate_recommendation_evidence.py"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert Path("docs/evidence/milestone-8/recommendation-manifest.json").exists()


def _config(input_dir: Path, tmp_path: Path, run_id: str) -> RecommendationConfig:
    return RecommendationConfig(
        input_dir=input_dir,
        output_root=tmp_path / "recommendations",
        run_id=run_id,
        snapshot_time=SNAPSHOT_TIME,
        lookback_days=56,
        holdout_days=28,
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


def _append_event(input_dir: Path, user_id: str, event_time: datetime) -> None:
    path = input_dir / "accepted" / "clickstream_events.jsonl"
    event = {
        "device_type": "desktop",
        "event_id": "test_post_snapshot_recommendation_event",
        "user_id": user_id,
        "session_id": "test_session",
        "event_timestamp": event_time.isoformat().replace("+00:00", "Z"),
        "event_name": "task_completed",
        "event_sequence_number": 1,
        "experiment_id": None,
        "experiment_variant": None,
        "journey_stage": "engagement",
        "page_name": "workspace",
        "feature_name": "tasks",
        "properties": {},
        "recommendation_id": None,
        "synthetic_record": True,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
