import csv
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from product_growth_intelligence.ingestion import IngestionConfig, run_batch_ingestion
from product_growth_intelligence.models.segmentation import SegmentationConfig, run_segmentation
from product_growth_intelligence.models.segmentation.pipeline import (
    assign_rule_based_segments,
    build_segmentation_rows,
    feature_catalogue,
)

FIXED_INGESTION_TIME = "2026-01-01T00:00:00Z"
FIXED_RUN_TIME = "2026-01-02T00:00:00Z"
SNAPSHOT_TIME = "2025-03-31T23:59:59Z"


def test_feature_catalogue_excludes_identifiers_from_clustering():
    catalogue = feature_catalogue()

    identifier_rows = [
        row for row in catalogue if row["feature_name"] in {"user_id", "snapshot_id"}
    ]

    assert identifier_rows
    assert all(row["clustering_role"] == "excluded" for row in identifier_rows)
    assert any(row["clustering_role"] == "clustering" for row in catalogue)


def test_invalid_segmentation_configuration_is_rejected():
    with pytest.raises(ValueError, match="lookback_days"):
        SegmentationConfig(
            input_dir=Path("unused"),
            output_root=Path("unused"),
            lookback_days=0,
        ).validate()

    with pytest.raises(ValueError, match="candidate cluster"):
        SegmentationConfig(
            input_dir=Path("unused"),
            output_root=Path("unused"),
            candidate_clusters=(1,),
        ).validate()


def test_post_snapshot_events_do_not_change_features(tmp_path: Path):
    input_dir = _ingest_sample(tmp_path)
    config = _config(input_dir, tmp_path, "before")
    before, _ = build_segmentation_rows(config)
    target = before[0]
    target_features = dict(target.features)
    _append_event(
        input_dir,
        target.snapshot.user_id,
        _parse_timestamp(target.snapshot.snapshot_timestamp) + timedelta(days=1),
    )

    after, _ = build_segmentation_rows(_config(input_dir, tmp_path, "after"))
    updated = [row for row in after if row.snapshot.snapshot_id == target.snapshot.snapshot_id][0]

    assert updated.features == target_features


def test_rule_assignments_are_mutually_exclusive(tmp_path: Path):
    input_dir = _ingest_sample(tmp_path)
    rows, _ = build_segmentation_rows(_config(input_dir, tmp_path, "rules"))
    assignments = assign_rule_based_segments(rows, "source")

    assert len(assignments) == len(rows)
    assert len({assignment.snapshot_id for assignment in assignments}) == len(rows)
    assert {assignment.rule_version for assignment in assignments} == {"2026-07-milestone-7-rules"}


def test_sample_segmentation_outputs_and_overwrite_refusal(tmp_path: Path):
    input_dir = _ingest_sample(tmp_path)
    config = _config(input_dir, tmp_path, "sample")

    result = run_segmentation(config)

    assert result.status == "passed"
    assert result.eligible_snapshots == 12
    assert result.selected_algorithm == "kmeans"
    assert result.selected_cluster_count >= 2
    output_dir = tmp_path / "segmentation" / "sample"
    assert (output_dir / "segmentation-manifest.json").exists()
    assignments = list(csv.DictReader((output_dir / "cluster-assignments.csv").open()))
    assert len(assignments) == result.eligible_snapshots
    assert all(float(row["distance_to_centroid"]) >= 0 for row in assignments)
    assert {row["business_segment_name"] for row in assignments}
    candidates = list(csv.DictReader((output_dir / "cluster-candidate-metrics.csv").open()))
    assert sum(1 for row in candidates if row["selected_status"] == "selected") == 1
    with pytest.raises(FileExistsError):
        run_segmentation(config)


def test_segmentation_cli_success(tmp_path: Path):
    input_dir = _ingest_sample(tmp_path)
    command = [
        sys.executable,
        "-m",
        "product_growth_intelligence",
        "segment-users",
        "--input-dir",
        str(input_dir),
        "--output-root",
        str(tmp_path / "segmentation"),
        "--run-id",
        "cli",
        "--snapshot-time",
        SNAPSHOT_TIME,
        "--lookback-days",
        "56",
        "--fixed-run-time",
        FIXED_RUN_TIME,
    ]

    result = subprocess.run(command, check=False, capture_output=True, text=True)

    assert result.returncode == 0
    assert "status: passed" in result.stdout
    assert "selected_cluster_count:" in result.stdout


def test_segmentation_evidence_generation_is_deterministic():
    result = subprocess.run(
        [sys.executable, "scripts/generate_segmentation_evidence.py"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert Path("docs/evidence/milestone-7/segmentation-manifest.json").exists()


def _config(input_dir: Path, tmp_path: Path, run_id: str) -> SegmentationConfig:
    return SegmentationConfig(
        input_dir=input_dir,
        output_root=tmp_path / "segmentation",
        run_id=run_id,
        snapshot_time=SNAPSHOT_TIME,
        lookback_days=56,
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
        "event_id": "test_post_snapshot_segmentation_event",
        "user_id": user_id,
        "session_id": "test_session",
        "event_timestamp": event_time.isoformat().replace("+00:00", "Z"),
        "event_name": "task_completed",
        "event_sequence_number": 1,
        "journey_stage": "engagement",
        "page_name": "workspace",
        "feature_name": "tasks",
        "properties": {},
        "synthetic_record": True,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
