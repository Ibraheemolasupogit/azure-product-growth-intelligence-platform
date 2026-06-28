import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from product_growth_intelligence.data_generation.catalogues import FEEDBACK_TEMPLATES
from product_growth_intelligence.data_generation.generator import generate_datasets
from product_growth_intelligence.data_generation.identifiers import stable_id
from product_growth_intelligence.data_generation.models import GenerationConfig
from product_growth_intelligence.data_generation.profiles import (
    default_generation_config,
    validate_generation_config,
)
from product_growth_intelligence.data_generation.validation import (
    SyntheticDataValidationError,
    validate_datasets,
)
from product_growth_intelligence.data_generation.writers import write_datasets


def test_generation_is_deterministic_for_same_seed(tmp_path: Path):
    first = generate_datasets(default_generation_config("sample", tmp_path / "one"))
    second = generate_datasets(default_generation_config("sample", tmp_path / "two"))

    assert first.by_name() == second.by_name()


def test_generation_changes_for_different_seed(tmp_path: Path):
    first_config = default_generation_config("sample", tmp_path / "one")
    second_base = default_generation_config("sample", tmp_path / "two")
    second_config = GenerationConfig(**{**second_base.__dict__, "seed": second_base.seed + 1})

    first = generate_datasets(first_config)
    second = generate_datasets(second_config)

    assert first.users != second.users


def test_stable_identifier_generation_is_repeatable():
    assert stable_id("usr", 42, 1) == stable_id("usr", 42, 1)
    assert stable_id("usr", 42, 1) != stable_id("usr", 43, 1)
    assert stable_id("usr", 42, 1).startswith("syn_usr_")


def test_configuration_validation_rejects_invalid_user_count(tmp_path: Path):
    base = default_generation_config("sample", tmp_path)
    invalid = GenerationConfig(**{**base.__dict__, "user_count": 0})

    with pytest.raises(ValueError, match="greater than zero"):
        validate_generation_config(invalid)


def test_configuration_validation_rejects_invalid_distribution(tmp_path: Path):
    base = default_generation_config("sample", tmp_path)
    invalid = GenerationConfig(
        **{**base.__dict__, "persona_distribution": {"solo_professional": 0.2}}
    )

    with pytest.raises(ValueError, match="sum to 1"):
        validate_generation_config(invalid)


def test_generated_records_include_required_fields(tmp_path: Path):
    datasets = generate_datasets(default_generation_config("sample", tmp_path))

    assert {
        "user_id",
        "signup_timestamp",
        "persona",
        "acquisition_channel",
        "synthetic_record",
    } <= set(datasets.users[0])
    assert {"event_id", "properties", "event_sequence_number"} <= set(
        datasets.clickstream_events[0]
    )
    assert isinstance(datasets.clickstream_events[0]["properties"], dict)


def test_cross_dataset_integrity_and_session_event_counts(tmp_path: Path):
    datasets = generate_datasets(default_generation_config("sample", tmp_path))
    event_counts = {
        session["session_id"]: sum(
            1
            for event in datasets.clickstream_events
            if event["session_id"] == session["session_id"]
        )
        for session in datasets.sessions
    }

    assert all(
        session["event_count"] == event_counts[session["session_id"]]
        for session in datasets.sessions
    )


def test_validation_rejects_unknown_event_user(tmp_path: Path):
    datasets = generate_datasets(default_generation_config("sample", tmp_path))
    datasets.clickstream_events[0]["user_id"] = "syn_usr_missing"

    with pytest.raises(SyntheticDataValidationError, match="unknown"):
        validate_datasets(datasets)


def test_validation_rejects_feature_usage_drift(tmp_path: Path):
    datasets = generate_datasets(default_generation_config("sample", tmp_path))
    datasets.feature_usage[0]["usage_count"] = int(datasets.feature_usage[0]["usage_count"]) + 1

    with pytest.raises(SyntheticDataValidationError, match="Feature usage"):
        validate_datasets(datasets)


def test_experiment_assignments_are_consistent(tmp_path: Path):
    datasets = generate_datasets(default_generation_config("sample", tmp_path))

    assert datasets.experiment_assignments
    for assignment in datasets.experiment_assignments:
        assert assignment["converted"] == isinstance(assignment["conversion_timestamp"], str)


def test_subscription_periods_do_not_overlap(tmp_path: Path):
    datasets = generate_datasets(default_generation_config("sample", tmp_path))

    by_user: dict[object, list[tuple[str, object]]] = {}
    for subscription in datasets.subscriptions:
        by_user.setdefault(subscription["user_id"], []).append(
            (str(subscription["period_start_timestamp"]), subscription["period_end_timestamp"])
        )

    for periods in by_user.values():
        ordered = sorted(periods)
        for current, next_period in zip(ordered, ordered[1:], strict=False):
            assert current[1] is not None
            assert str(current[1]) <= next_period[0]


def test_feedback_uses_controlled_templates(tmp_path: Path):
    datasets = generate_datasets(default_generation_config("sample", tmp_path))
    allowed_text = {text for templates in FEEDBACK_TEMPLATES.values() for text in templates}
    sentiments = {feedback["synthetic_sentiment_label"] for feedback in datasets.customer_feedback}

    assert {"positive", "neutral", "negative"} <= sentiments
    assert all(feedback["feedback_text"] in allowed_text for feedback in datasets.customer_feedback)


def test_writer_outputs_manifest_checksums_and_json_objects(tmp_path: Path):
    config = default_generation_config("sample", tmp_path / "run")
    datasets = generate_datasets(config)
    result = write_datasets(datasets, config)

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    users_rows = list(csv.DictReader((config.output_dir / "users.csv").open(encoding="utf-8")))
    first_event = json.loads(
        (config.output_dir / "clickstream_events.jsonl").read_text().splitlines()[0]
    )

    assert manifest["datasets"]["users.csv"]["row_count"] == len(users_rows)
    assert first_event["properties"] == datasets.clickstream_events[0]["properties"]
    for dataset_name, metadata in manifest["datasets"].items():
        digest = hashlib.sha256((config.output_dir / dataset_name).read_bytes()).hexdigest()
        assert metadata["sha256"] == digest


def test_cli_success_and_refuses_overwrite(tmp_path: Path):
    output_dir = tmp_path / "cli-run"
    command = [
        sys.executable,
        "-m",
        "product_growth_intelligence",
        "generate-data",
        "--profile",
        "sample",
        "--output-dir",
        str(output_dir),
    ]

    first = subprocess.run(command, cwd=Path.cwd(), check=False, capture_output=True, text=True)
    second = subprocess.run(command, cwd=Path.cwd(), check=False, capture_output=True, text=True)

    assert first.returncode == 0
    assert "users.csv: 12 rows" in first.stdout
    assert second.returncode != 0
    assert "already exists" in second.stderr
