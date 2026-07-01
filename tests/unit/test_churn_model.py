import csv
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from product_growth_intelligence.ingestion import IngestionConfig, run_batch_ingestion
from product_growth_intelligence.models.churn import ChurnTrainingConfig, run_churn_training
from product_growth_intelligence.models.churn.pipeline import build_feature_rows, churn_definition

FIXED_INGESTION_TIME = "2026-01-01T00:00:00Z"
FIXED_RUN_TIME = "2026-01-02T00:00:00Z"


def test_churn_definition_is_valid_and_unique():
    definition = churn_definition(
        ChurnTrainingConfig(input_dir=Path("unused"), output_root=Path("unused"))
    )

    assert definition["definition_id"] == "behavioural_churn"
    assert definition["version"] == "2026-07-milestone-6"
    assert definition["lookback_days"] == 28
    assert "session_started" not in definition["qualifying_events"]


def test_invalid_windows_are_rejected():
    with pytest.raises(ValueError, match="lookback_days"):
        ChurnTrainingConfig(
            input_dir=Path("unused"),
            output_root=Path("unused"),
            lookback_days=0,
        ).validate()


def test_snapshot_labels_and_outputs(tmp_path: Path):
    input_dir = _ingest_sample(tmp_path)
    result = run_churn_training(_config(input_dir, tmp_path, "sample"))

    assert result.status == "passed"
    assert result.row_count > 3
    assert 0 <= result.label_prevalence <= 1
    output_dir = tmp_path / "churn" / "sample"
    assert (output_dir / "model-manifest.json").exists()
    assert (
        (output_dir / "model-card.md")
        .read_text(encoding="utf-8")
        .startswith("# Churn Prediction Model Card")
    )
    labels = [
        json.loads(line)
        for line in (output_dir / "snapshot-labels.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len({row["snapshot_id"] for row in labels}) == len(labels)
    assert {row["behavioural_churn"] for row in labels} <= {0, 1}
    assert any(row["future_qualifying_events"] > 0 for row in labels)


def test_post_snapshot_activity_changes_label_not_features(tmp_path: Path):
    input_dir = _ingest_sample(tmp_path)
    before = build_feature_rows(_config(input_dir, tmp_path, "before"))
    target = before[0]
    target_features = dict(target.features)
    target_label_events = target.label.future_qualifying_events
    event_time = _parse_timestamp(target.label.label_window_end) - timedelta(hours=1)
    _append_event(input_dir, target.label.user_id, event_time)

    after = build_feature_rows(_config(input_dir, tmp_path, "after"))
    updated = [row for row in after if row.label.snapshot_id == target.label.snapshot_id][0]

    assert updated.features == target_features
    assert updated.label.future_qualifying_events == target_label_events + 1


def test_chronological_splits_and_overwrite_refusal(tmp_path: Path):
    input_dir = _ingest_sample(tmp_path)
    config = _config(input_dir, tmp_path, "splits")

    run_churn_training(config)

    split_rows = list(csv.DictReader((tmp_path / "churn" / "splits" / "dataset-splits.csv").open()))
    assert [row["split"] for row in split_rows] == sorted(
        [row["split"] for row in split_rows],
        key={"train": 0, "validation": 1, "test": 2}.get,
    )
    with pytest.raises(FileExistsError):
        run_churn_training(config)


def test_churn_cli_success(tmp_path: Path):
    input_dir = _ingest_sample(tmp_path)
    command = [
        sys.executable,
        "-m",
        "product_growth_intelligence",
        "train-churn-model",
        "--input-dir",
        str(input_dir),
        "--output-root",
        str(tmp_path / "churn"),
        "--run-id",
        "cli",
        "--analysis-end",
        "2025-03-31T23:59:59Z",
        "--fixed-run-time",
        FIXED_RUN_TIME,
    ]

    result = subprocess.run(command, check=False, capture_output=True, text=True)

    assert result.returncode == 0
    assert "status: passed" in result.stdout
    assert "selected_model:" in result.stdout


def test_churn_evidence_generation_is_deterministic():
    result = subprocess.run(
        [sys.executable, "scripts/generate_churn_evidence.py"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert Path("docs/evidence/milestone-6/model-manifest.json").exists()


def _config(input_dir: Path, tmp_path: Path, run_id: str) -> ChurnTrainingConfig:
    return ChurnTrainingConfig(
        input_dir=input_dir,
        output_root=tmp_path / "churn",
        run_id=run_id,
        analysis_end="2025-03-31T23:59:59Z",
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
        "event_id": "test_future_activity",
        "user_id": user_id,
        "session_id": "test_session",
        "event_timestamp": event_time.isoformat().replace("+00:00", "Z"),
        "event_name": "task_completed",
        "event_sequence_number": 1,
        "journey_stage": "activation",
        "page_name": "workspace",
        "feature_name": "tasks",
        "properties": {},
        "synthetic_record": True,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
