import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from product_growth_intelligence.data_generation import (
    default_generation_config,
    generate_datasets,
    write_datasets,
)
from product_growth_intelligence.ingestion import IngestionConfig, run_batch_ingestion
from product_growth_intelligence.ingestion.fingerprints import record_fingerprint
from product_growth_intelligence.ingestion.parsers import parse_csv, parse_jsonl
from product_growth_intelligence.ingestion.streaming import run_stream_ingestion
from product_growth_intelligence.validation.contracts import CONTRACTS, writer_columns_for

SAMPLE = Path("data/samples/nexaflow")
FIXED_TIME = "2026-01-01T00:00:00Z"


def test_contracts_align_with_writer_columns_and_sample_records():
    for contract in CONTRACTS.values():
        assert contract.field_names == writer_columns_for(contract)
        assert (SAMPLE / contract.filename).exists()


def test_valid_sample_batch_ingestion_writes_reports(tmp_path: Path):
    result = run_batch_ingestion(
        IngestionConfig(
            source=SAMPLE,
            output_root=tmp_path / "interim",
            quality_root=tmp_path / "quality",
            run_id="valid",
            fixed_ingestion_time=FIXED_TIME,
        )
    )

    assert result.status == "passed"
    assert result.accepted_count == 964
    assert result.quarantined_count == 0
    assert result.manifest_path is not None and result.manifest_path.exists()
    assert result.lineage_path is not None and result.lineage_path.exists()
    report = json.loads((tmp_path / "quality" / "valid" / "quality-report.json").read_text())
    assert report["summary"]["accepted_records"] == 964


def test_source_manifest_checksum_mismatch_fails(tmp_path: Path):
    source = _copy_sample(tmp_path)
    users = source / "users.csv"
    users.write_text(users.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    result = run_batch_ingestion(
        IngestionConfig(
            source=source,
            output_root=tmp_path / "interim",
            quality_root=tmp_path / "quality",
            run_id="checksum",
            fixed_ingestion_time=FIXED_TIME,
            max_quarantine_rate=1.0,
        )
    )

    assert result.status == "failed"
    assert any(
        rule.rule_id == "MANIFEST_CHECKSUM_MISMATCH"
        for rule in result.dataset_results["users"].rules
    )


def test_csv_parser_reports_missing_required_and_type_errors(tmp_path: Path):
    path = tmp_path / "users.csv"
    path.write_text(
        "user_id,signup_timestamp,country,region,acquisition_channel,device_preference,"
        "persona,company_size_band,initial_plan,marketing_consent,is_team_account,"
        "synthetic_record\n"
        "syn_usr_bad,,Canada,North America,organic_search,desktop,solo_professional,"
        "solo,free,not-bool,False,True\n",
        encoding="utf-8",
    )

    parsed, _, _ = parse_csv(path, CONTRACTS["users"], "strict")

    assert parsed[0].record is None
    assert {rule.rule_id for rule in parsed[0].parse_errors} == {
        "FIELD_REQUIRED",
        "FIELD_TYPE_INVALID",
    }


def test_jsonl_parser_quarantines_malformed_json_and_non_object(tmp_path: Path):
    path = tmp_path / "clickstream_events.jsonl"
    path.write_text("{bad json\n[]\n\n", encoding="utf-8")

    parsed, _, _ = parse_jsonl(path, CONTRACTS["clickstream_events"], "strict")

    assert [record.parse_errors[0].rule_id for record in parsed] == [
        "JSONL_MALFORMED",
        "JSONL_NON_OBJECT",
        "JSONL_BLANK_LINE",
    ]


def test_stable_record_fingerprints_support_nested_properties():
    first = {"event_id": "a", "properties": {"b": 1, "a": True}}
    second = {"properties": {"a": True, "b": 1}, "event_id": "a"}
    changed = {"event_id": "a", "properties": {"b": 2, "a": True}}

    assert record_fingerprint(first) == record_fingerprint(second)
    assert record_fingerprint(first) != record_fingerprint(changed)


def test_duplicate_policy_reject_quarantines_duplicate_primary_key(tmp_path: Path):
    source = _copy_sample(tmp_path)
    users = (source / "users.csv").read_text(encoding="utf-8").splitlines()
    (source / "users.csv").write_text("\n".join([*users, users[1]]) + "\n", encoding="utf-8")
    (source / "manifest.json").unlink()

    result = run_batch_ingestion(
        IngestionConfig(
            source=source,
            output_root=tmp_path / "interim",
            quality_root=tmp_path / "quality",
            run_id="dupe",
            fixed_ingestion_time=FIXED_TIME,
            max_quarantine_rate=1.0,
        )
    )

    assert result.status == "failed"
    assert result.dataset_results["users"].quarantined_count == 1
    assert any(
        rule.rule_id == "DUPLICATE_PRIMARY_KEY" for rule in result.dataset_results["users"].rules
    )


def test_schema_drift_report_only_warns_without_rejecting(tmp_path: Path):
    source = _copy_sample(tmp_path)
    users = (source / "users.csv").read_text(encoding="utf-8").splitlines()
    users[0] = f"{users[0]},new_optional"
    users[1:] = [f"{line},value" for line in users[1:]]
    (source / "users.csv").write_text("\n".join(users) + "\n", encoding="utf-8")
    (source / "manifest.json").unlink()

    result = run_batch_ingestion(
        IngestionConfig(
            source=source,
            output_root=tmp_path / "interim",
            quality_root=tmp_path / "quality",
            run_id="drift",
            schema_policy="report-only",
            fixed_ingestion_time=FIXED_TIME,
        )
    )

    assert result.status == "passed"
    assert result.dataset_results["users"].schema_drift[0].drift_type == "additive_unknown_column"


def test_referential_and_temporal_failures_quarantine_records(tmp_path: Path):
    source = _copy_sample(tmp_path)
    events = (source / "clickstream_events.jsonl").read_text(encoding="utf-8").splitlines()
    first = json.loads(events[0])
    first["session_id"] = "syn_ses_missing"
    events[0] = json.dumps(first, sort_keys=True)
    second = json.loads(events[1])
    second["event_timestamp"] = "2030-01-01T00:00:00Z"
    events[1] = json.dumps(second, sort_keys=True)
    (source / "clickstream_events.jsonl").write_text("\n".join(events) + "\n", encoding="utf-8")
    (source / "manifest.json").unlink()

    result = run_batch_ingestion(
        IngestionConfig(
            source=source,
            output_root=tmp_path / "interim",
            quality_root=tmp_path / "quality",
            run_id="cross",
            fixed_ingestion_time=FIXED_TIME,
            max_quarantine_rate=1.0,
        )
    )

    assert result.status == "failed"
    assert result.dataset_results["clickstream_events"].quarantined_count >= 2
    rule_ids = {rule.rule_id for rule in result.dataset_results["clickstream_events"].rules}
    assert {"FK_SESSION_MISSING", "EVENT_OUTSIDE_SESSION"} <= rule_ids


def test_subscription_overlap_detection(tmp_path: Path):
    source = _copy_sample(tmp_path)
    rows = (source / "subscriptions.csv").read_text(encoding="utf-8").splitlines()
    duplicate = rows[1].replace("syn_sub_", "syn_sub_overlap_", 1)
    (source / "subscriptions.csv").write_text(
        "\n".join([*rows, duplicate]) + "\n", encoding="utf-8"
    )
    (source / "manifest.json").unlink()

    result = run_batch_ingestion(
        IngestionConfig(
            source=source,
            output_root=tmp_path / "interim",
            quality_root=tmp_path / "quality",
            run_id="overlap",
            fixed_ingestion_time=FIXED_TIME,
            max_quarantine_rate=1.0,
        )
    )

    assert any(
        rule.rule_id == "SUBSCRIPTION_PERIOD_OVERLAP"
        for rule in result.dataset_results["subscriptions"].rules
    )


def test_stream_ingestion_accepts_valid_events_and_rejects_bad_event(tmp_path: Path):
    source = tmp_path / "clickstream_events.jsonl"
    events = (SAMPLE / "clickstream_events.jsonl").read_text(encoding="utf-8").splitlines()[:3]
    bad = json.loads(events[0])
    bad["event_name"] = "unknown_event"
    source.write_text("\n".join([*events, json.dumps(bad)]) + "\n", encoding="utf-8")

    result = run_stream_ingestion(
        IngestionConfig(
            source=source,
            output_root=tmp_path / "stream",
            quality_root=tmp_path / "quality",
            run_id="stream",
            mode="stream",
            fixed_ingestion_time=FIXED_TIME,
            stream_micro_batch_size=2,
            max_quarantine_rate=1.0,
        )
    )

    assert result.status == "failed"
    assert result.dataset_results["clickstream_events"].accepted_count == 3
    assert result.dataset_results["clickstream_events"].quarantined_count == 1


def test_idempotency_refuses_existing_output_without_overwrite(tmp_path: Path):
    config = IngestionConfig(
        source=SAMPLE,
        output_root=tmp_path / "interim",
        quality_root=tmp_path / "quality",
        run_id="same",
        fixed_ingestion_time=FIXED_TIME,
    )
    run_batch_ingestion(config)

    with pytest.raises(FileExistsError):
        run_batch_ingestion(config)


def test_batch_cli_success_and_failure_status(tmp_path: Path):
    success = subprocess.run(
        [
            sys.executable,
            "-m",
            "product_growth_intelligence",
            "ingest-batch",
            "--source",
            str(SAMPLE),
            "--output-root",
            str(tmp_path / "interim"),
            "--quality-root",
            str(tmp_path / "quality"),
            "--run-id",
            "cli-ok",
            "--fixed-ingestion-time",
            FIXED_TIME,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert success.returncode == 0
    assert "accepted: 964" in success.stdout

    source = _copy_sample(tmp_path / "bad")
    events = (source / "clickstream_events.jsonl").read_text(encoding="utf-8").splitlines()
    bad = json.loads(events[0])
    bad["event_name"] = "unknown_event"
    events[0] = json.dumps(bad)
    (source / "clickstream_events.jsonl").write_text("\n".join(events) + "\n", encoding="utf-8")
    (source / "manifest.json").unlink()
    failure = subprocess.run(
        [
            sys.executable,
            "-m",
            "product_growth_intelligence",
            "ingest-batch",
            "--source",
            str(source),
            "--output-root",
            str(tmp_path / "interim"),
            "--quality-root",
            str(tmp_path / "quality"),
            "--run-id",
            "cli-fail",
            "--fixed-ingestion-time",
            FIXED_TIME,
            "--max-quarantine-rate",
            "1",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert failure.returncode == 1
    assert "status: failed" in failure.stdout


def test_generation_sample_still_regenerates(tmp_path: Path):
    config = default_generation_config("sample", tmp_path / "generated")
    result = write_datasets(generate_datasets(config), config)

    assert result.row_counts["clickstream_events.jsonl"] == 591


def _copy_sample(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    shutil.copytree(SAMPLE, source)
    return source
