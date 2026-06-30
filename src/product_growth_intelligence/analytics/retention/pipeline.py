"""Retention and cohort analysis pipeline."""

from __future__ import annotations

from datetime import UTC, datetime

from product_growth_intelligence.analytics.inputs import load_trusted_input
from product_growth_intelligence.analytics.retention.cohorts import (
    build_memberships,
    build_user_period_activity,
)
from product_growth_intelligence.analytics.retention.definitions import (
    default_retention_definitions,
    definitions_by_id,
    validate_retention_definitions,
)
from product_growth_intelligence.analytics.retention.metrics import (
    cohort_summary_rows,
    lifecycle_rows,
    resurrection_rows,
    retention_long_rows,
    retention_matrix_rows,
    segment_retention_rows,
)
from product_growth_intelligence.analytics.retention.models import (
    RetentionAnalysisConfig,
    RetentionAnalysisResult,
)
from product_growth_intelligence.analytics.retention.validation import validate_retention_outputs
from product_growth_intelligence.analytics.retention.writers import (
    prepare_output_dir,
    write_outputs,
)
from product_growth_intelligence.ingestion.fingerprints import record_fingerprint


def run_retention_analysis(config: RetentionAnalysisConfig) -> RetentionAnalysisResult:
    """Run governed retention analytics."""

    all_definitions = definitions_by_id(
        default_retention_definitions(config.time_grain, config.horizon)
    )
    config.validate(set(all_definitions))
    definitions = tuple(
        all_definitions[definition_id]
        for definition_id in (config.enabled_definitions or tuple(sorted(all_definitions)))
    )
    validate_retention_definitions(definitions)
    run_id = config.run_id or _derive_run_id(config)
    output_dir = prepare_output_dir(config, run_id)
    trusted = load_trusted_input(config.input_dir)
    memberships = build_memberships(
        trusted, definitions, config.analysis_start, config.analysis_end
    )
    user_periods = build_user_period_activity(
        trusted, definitions, memberships, config.analysis_end
    )
    long_rows = retention_long_rows(
        definitions, memberships, user_periods, config.suppression_threshold
    )
    matrix_rows = retention_matrix_rows(long_rows)
    summary_rows = cohort_summary_rows(definitions, memberships, user_periods)
    segment_rows, suppressed_segments = segment_retention_rows(
        memberships, user_periods, config.segment_dimensions, config.suppression_threshold
    )
    lifecycle = lifecycle_rows(
        memberships, user_periods, config.inactivity_threshold, config.churn_threshold
    )
    resurrection = resurrection_rows(lifecycle)
    validate_retention_outputs(memberships, user_periods, long_rows)
    diagnostics: dict[str, object] = {
        "input_compatibility_checks": "passed",
        "definitions_evaluated": [definition.definition_id for definition in definitions],
        "cohort_memberships": len(memberships),
        "cohort_periods": len({membership.cohort_period for membership in memberships}),
        "user_period_rows": len(user_periods),
        "censored_cells": sum(1 for row in long_rows if int(row["censored_users"]) > 0),
        "zero_denominators": sum(1 for row in long_rows if int(row["observed_denominator"]) == 0),
        "suppressed_segment_rows": suppressed_segments,
        "reconciliation_results": "passed",
        "invalid_definitions": [],
        "warnings": [],
        "overall_status": "passed",
    }
    if not config.validate_only:
        write_outputs(
            output_dir,
            config=config,
            run_id=run_id,
            trusted=trusted,
            definitions=definitions,
            memberships=memberships,
            user_periods=user_periods,
            matrix_rows=matrix_rows,
            long_rows=long_rows,
            cohort_summary_rows=summary_rows,
            segment_rows=segment_rows,
            lifecycle_rows=lifecycle,
            resurrection_rows=resurrection,
            diagnostics=diagnostics,
        )
    return RetentionAnalysisResult(
        run_id=run_id,
        status=str(diagnostics["overall_status"]),
        output_dir=output_dir,
        memberships=memberships,
        user_periods=user_periods,
        retention_long_rows=long_rows,
        cohort_summary_rows=summary_rows,
        diagnostics=diagnostics,
    )


def _derive_run_id(config: RetentionAnalysisConfig) -> str:
    created = config.fixed_analysis_time or datetime.now(UTC).replace(microsecond=0).isoformat()
    return (
        "retention-"
        + record_fingerprint(
            {
                "input": str(config.input_dir),
                "grain": config.time_grain,
                "horizon": config.horizon,
                "analysis_start": config.analysis_start,
                "analysis_end": config.analysis_end,
                "created": created,
            }
        )[:12]
    )
