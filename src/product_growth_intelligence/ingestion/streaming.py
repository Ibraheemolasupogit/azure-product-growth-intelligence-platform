"""Deterministic local streaming simulation for clickstream events."""

from __future__ import annotations

from product_growth_intelligence.ingestion.batch import (
    _classify_record,
    _refresh_counts,
    _status_for,
)
from product_growth_intelligence.ingestion.metadata import derive_run_id, ingestion_time
from product_growth_intelligence.ingestion.models import (
    DatasetIngestionResult,
    IngestionConfig,
    PipelineResult,
)
from product_growth_intelligence.ingestion.parsers import parse_jsonl
from product_growth_intelligence.ingestion.writers import (
    make_pipeline_result,
    prepare_output_dirs,
    write_dataset_outputs,
    write_metrics,
    write_quality_outputs,
)
from product_growth_intelligence.validation.contracts import CONTRACTS


def run_stream_ingestion(config: IngestionConfig) -> PipelineResult:
    """Run local micro-batch stream ingestion for clickstream events."""

    config.validate()
    if not config.source.exists() or not config.source.is_file():
        msg = f"Source event file {config.source} does not exist."
        raise FileNotFoundError(msg)
    run_id = derive_run_id(config)
    output_dir, quality_dir = prepare_output_dirs(config, run_id)
    ingested_at = ingestion_time(config)
    contract = CONTRACTS["clickstream_events"]
    parsed_records, schema_findings, file_rules = parse_jsonl(
        config.source, contract, config.schema_policy
    )
    result = DatasetIngestionResult(
        dataset="clickstream_events",
        schema_drift=list(schema_findings),
        rules=list(file_rules),
        source_count=len(parsed_records),
    )
    micro_batches = 0
    for index in range(0, len(parsed_records), config.stream_micro_batch_size):
        micro_batches += 1
        for parsed in parsed_records[index : index + config.stream_micro_batch_size]:
            _classify_record(
                result,
                parsed,
                contract,
                run_id,
                ingested_at,
                source_generation_run_id=None,
            )
    _refresh_counts({"clickstream_events": result})
    status = _status_for(result.rules)
    if not config.validate_only:
        write_dataset_outputs(output_dir, result)
        quality_json, quality_md = write_quality_outputs(
            quality_dir,
            run_id=run_id,
            status=status,
            dataset_results={"clickstream_events": result},
            all_rules=result.rules,
        )
        metrics_path = write_metrics(
            quality_dir,
            files_discovered=1,
            dataset_results={"clickstream_events": result},
            stream_micro_batches=micro_batches,
        )
    else:
        quality_json = None
        quality_md = None
        metrics_path = None
    return make_pipeline_result(
        run_id=run_id,
        status=status,
        output_dir=output_dir,
        quality_dir=quality_dir,
        dataset_results={"clickstream_events": result},
        manifest_path=None,
        quality_report_json_path=quality_json,
        quality_report_md_path=quality_md,
        lineage_path=None,
        metrics_path=metrics_path,
    )
