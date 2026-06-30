"""Governed funnel analytics pipeline."""

from __future__ import annotations

from datetime import UTC, datetime

from product_growth_intelligence.analytics.funnel_definitions import (
    default_funnel_definitions,
    definitions_by_id,
    validate_funnel_definitions,
)
from product_growth_intelligence.analytics.funnel_models import (
    FunnelAnalysisConfig,
    FunnelAnalysisResult,
)
from product_growth_intelligence.analytics.inputs import load_trusted_input
from product_growth_intelligence.analytics.journey import reconstruct_attempts
from product_growth_intelligence.analytics.metrics import (
    calculate_dropoff_rows,
    calculate_segment_rows,
    calculate_stage_rows,
    calculate_summary_rows,
    calculate_time_rows,
    diagnostic_payload,
)
from product_growth_intelligence.analytics.validation import validate_attempts, validate_metric_rows
from product_growth_intelligence.analytics.writers import (
    prepare_analysis_output_dir,
    write_analysis_outputs,
)
from product_growth_intelligence.ingestion.fingerprints import record_fingerprint


def run_funnel_analysis(config: FunnelAnalysisConfig) -> FunnelAnalysisResult:
    """Run the local governed funnel analytics pipeline."""

    all_definitions = definitions_by_id()
    config.validate(set(all_definitions))
    definitions = tuple(
        all_definitions[funnel_id]
        for funnel_id in (config.enabled_funnels or tuple(sorted(all_definitions)))
    )
    validate_funnel_definitions(definitions)
    run_id = config.run_id or _derive_run_id(config)
    output_dir = prepare_analysis_output_dir(config, run_id)
    trusted = load_trusted_input(config.input_dir)
    attempts, eligible_counts, warnings = reconstruct_attempts(
        trusted,
        definitions,
        config.analysis_start,
        config.analysis_end,
    )
    validate_attempts(attempts)
    summary_rows = calculate_summary_rows(
        definitions, attempts, eligible_counts, config.analysis_start, config.analysis_end
    )
    stage_rows = calculate_stage_rows(definitions, attempts, eligible_counts)
    time_rows = calculate_time_rows(definitions, attempts)
    segment_rows, suppressed_segments = calculate_segment_rows(
        definitions,
        attempts,
        eligible_counts,
        config.segment_dimensions,
        config.suppression_threshold,
    )
    dropoff_rows = calculate_dropoff_rows(definitions, attempts)
    validate_metric_rows(summary_rows, stage_rows)
    diagnostics = diagnostic_payload(definitions, attempts, suppressed_segments)
    if warnings:
        diagnostics["definition_warnings"] = list(warnings)
        diagnostics["overall_status"] = "passed_with_warnings"
    if not config.validate_only:
        write_analysis_outputs(
            output_dir,
            config=config,
            run_id=run_id,
            trusted=trusted,
            definitions=definitions,
            attempts=attempts,
            summary_rows=summary_rows,
            stage_rows=stage_rows,
            segment_rows=segment_rows,
            time_rows=time_rows,
            dropoff_rows=dropoff_rows,
            diagnostics=diagnostics,
        )
    return FunnelAnalysisResult(
        run_id=run_id,
        status=str(diagnostics["overall_status"]),
        output_dir=output_dir,
        attempts=attempts,
        summary_rows=summary_rows,
        stage_rows=stage_rows,
        segment_rows=segment_rows,
        time_rows=time_rows,
        dropoff_rows=dropoff_rows,
        diagnostics=diagnostics,
    )


def _derive_run_id(config: FunnelAnalysisConfig) -> str:
    created = config.fixed_analysis_time or datetime.now(UTC).replace(microsecond=0).isoformat()
    return (
        "funnels-"
        + record_fingerprint(
            {
                "input": str(config.input_dir),
                "analysis_start": config.analysis_start,
                "analysis_end": config.analysis_end,
                "created": created,
            }
        )[:12]
    )


__all__ = ["default_funnel_definitions", "run_funnel_analysis"]
