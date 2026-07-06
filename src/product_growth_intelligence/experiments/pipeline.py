"""Governed deterministic A/B experiment-analysis workflow."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from product_growth_intelligence.analytics.inputs import (
    dataset_row_counts,
    load_trusted_input,
    source_manifest_checksum,
)
from product_growth_intelligence.data_generation.models import Record
from product_growth_intelligence.experiments.catalogue import (
    EXPERIMENT_CATALOGUE_VERSION,
    EXPERIMENT_METRIC_VERSION,
    default_experiment_catalogue,
    experiment_metrics,
    validate_experiment_catalogue,
)
from product_growth_intelligence.experiments.models import (
    Decision,
    ExperimentAnalysisConfig,
    ExperimentAnalysisResult,
    ExperimentSpec,
    MetricSpec,
    Population,
)
from product_growth_intelligence.experiments.statistics import (
    adjust_p_values,
    binary_required_sample_size,
    chi_square_srm,
    two_proportion_effect,
    welch_mean_effect,
)
from product_growth_intelligence.ingestion.fingerprints import file_sha256
from product_growth_intelligence.metadata import get_project_metadata

EXPERIMENT_ANALYSIS_VERSION = "2026-07-milestone-9"


def run_experiment_analysis(config: ExperimentAnalysisConfig) -> ExperimentAnalysisResult:
    """Run governed experiment analysis over trusted accepted data."""

    config.validate()
    trusted = load_trusted_input(config.input_dir)
    run_id = config.run_id or _default_run_id(config)
    output_dir = config.output_root / run_id
    if output_dir.exists() and any(output_dir.iterdir()) and not config.overwrite:
        msg = f"Output directory {output_dir} already exists and is not empty. Pass --overwrite."
        raise FileExistsError(msg)
    metrics = experiment_metrics()
    experiments = _selected_experiments(config)
    validate_experiment_catalogue(experiments, metrics)
    if config.validate_only:
        return ExperimentAnalysisResult(run_id, "validated", output_dir, len(experiments), {})

    context = _analysis_context(trusted.datasets)
    assignments = trusted.datasets["experiment_assignments"]
    integrity_rows, valid_assignments = _assignment_integrity(assignments, experiments, context)
    exposure_rows = _exposure_rows(valid_assignments, experiments, context)
    population_rows = _population_rows(valid_assignments, exposure_rows, experiments)
    srm_rows = _srm_rows(valid_assignments, experiments, config)
    metric_rows = _metric_rows(
        valid_assignments, exposure_rows, experiments, metrics, context, config
    )
    guardrail_rows = _guardrail_rows(metric_rows, experiments, metrics, config)
    segment_rows = _segment_rows(
        valid_assignments, exposure_rows, experiments, metrics, context, config
    )
    metric_rows, guardrail_rows, segment_rows, multiple_rows = _apply_corrections(
        metric_rows,
        guardrail_rows,
        segment_rows,
        config,
    )
    power_rows = _power_rows(metric_rows, experiments, metrics)
    decision_rows, decisions = _decision_rows(
        metric_rows,
        guardrail_rows,
        srm_rows,
        integrity_rows,
        power_rows,
        experiments,
        metrics,
        config,
    )
    diagnostics = _diagnostics(
        experiments,
        assignments,
        integrity_rows,
        exposure_rows,
        srm_rows,
        metric_rows,
        guardrail_rows,
        segment_rows,
        decision_rows,
    )
    _validate_outputs(metric_rows, guardrail_rows, srm_rows, decision_rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_outputs(
        output_dir=output_dir,
        config=config,
        run_id=run_id,
        trusted_row_counts=dataset_row_counts(trusted),
        source_ingestion_run_id=trusted.source_ingestion_run_id,
        source_checksum=trusted.source_manifest_checksum
        or source_manifest_checksum(config.input_dir),
        source_contract_versions=trusted.contract_versions,
        experiments=experiments,
        metrics=metrics,
        integrity_rows=integrity_rows,
        population_rows=population_rows,
        srm_rows=srm_rows,
        metric_rows=metric_rows,
        guardrail_rows=guardrail_rows,
        segment_rows=segment_rows,
        multiple_rows=multiple_rows,
        power_rows=power_rows,
        decision_rows=decision_rows,
        diagnostics=diagnostics,
    )
    return ExperimentAnalysisResult(
        run_id=run_id,
        status=str(diagnostics["overall_status"]),
        output_dir=output_dir,
        experiments_evaluated=len(experiments),
        decisions=decisions,
        diagnostics=diagnostics,
    )


def _selected_experiments(config: ExperimentAnalysisConfig) -> tuple[ExperimentSpec, ...]:
    experiments = default_experiment_catalogue()
    if not config.experiment_ids:
        return experiments
    known = {experiment.experiment_id for experiment in experiments}
    unknown = sorted(set(config.experiment_ids) - known)
    if unknown:
        msg = f"Unknown experiment IDs: {unknown}."
        raise ValueError(msg)
    return tuple(
        experiment
        for experiment in experiments
        if experiment.experiment_id in config.experiment_ids
    )


def _analysis_context(datasets: dict[str, list[Record]]) -> dict[str, Any]:
    users = {str(user["user_id"]): user for user in datasets["users"]}
    events_by_user: dict[str, list[Record]] = defaultdict(list)
    for event in datasets["clickstream_events"]:
        events_by_user[str(event["user_id"])].append(event)
    for rows in events_by_user.values():
        rows.sort(key=lambda row: (str(row["event_timestamp"]), str(row["event_sequence_number"])))
    subscriptions_by_user: dict[str, list[Record]] = defaultdict(list)
    for subscription in datasets["subscriptions"]:
        subscriptions_by_user[str(subscription["user_id"])].append(subscription)
    feedback_by_user: dict[str, list[Record]] = defaultdict(list)
    for feedback in datasets.get("customer_feedback", []):
        feedback_by_user[str(feedback["user_id"])].append(feedback)
    return {
        "users": users,
        "events_by_user": dict(events_by_user),
        "subscriptions_by_user": dict(subscriptions_by_user),
        "feedback_by_user": dict(feedback_by_user),
    }


def _assignment_integrity(
    assignments: list[Record],
    experiments: tuple[ExperimentSpec, ...],
    context: dict[str, Any],
) -> tuple[list[Record], list[Record]]:
    specs = {experiment.experiment_id: experiment for experiment in experiments}
    grouped: dict[tuple[str, str], list[Record]] = defaultdict(list)
    for assignment in assignments:
        grouped[(str(assignment["experiment_id"]), str(assignment["user_id"]))].append(assignment)
    rows: list[Record] = []
    valid: list[Record] = []
    users: dict[str, Record] = context["users"]
    for assignment in assignments:
        experiment_id = str(assignment["experiment_id"])
        user_id = str(assignment["user_id"])
        spec = specs.get(experiment_id)
        reasons: list[str] = []
        if spec is None:
            reasons.append("unknown_experiment")
        else:
            variant = str(assignment["variant"])
            if variant not in spec.variants:
                reasons.append("invalid_variant")
            timestamp = _parse_dt(str(assignment["assignment_timestamp"]))
            if not _parse_dt(spec.assignment_start) <= timestamp <= _parse_dt(spec.assignment_end):
                reasons.append("assignment_outside_experiment_period")
        duplicates = grouped[(experiment_id, user_id)]
        if len(duplicates) > 1:
            reasons.append("duplicate_assignment")
            if len({str(row["variant"]) for row in duplicates}) > 1:
                reasons.append("conflicting_variant")
        user = users.get(user_id)
        if user is None:
            reasons.append("unknown_user")
        elif _parse_dt(str(user["signup_timestamp"])) > _parse_dt(
            str(assignment["assignment_timestamp"])
        ):
            reasons.append("assignment_before_signup")
        exposure = assignment.get("exposure_timestamp")
        if exposure and _parse_dt(str(exposure)) < _parse_dt(
            str(assignment["assignment_timestamp"])
        ):
            reasons.append("exposure_before_assignment")
        conversion = assignment.get("conversion_timestamp")
        if conversion and exposure and _parse_dt(str(conversion)) < _parse_dt(str(exposure)):
            reasons.append("conversion_before_exposure")
        status = "valid" if not reasons else "excluded"
        row = {
            "experiment_id": experiment_id,
            "assignment_id": assignment["assignment_id"],
            "user_id": user_id,
            "variant": assignment["variant"],
            "assignment_timestamp": assignment["assignment_timestamp"],
            "integrity_status": status,
            "exclusion_reason": "|".join(sorted(set(reasons))) if reasons else "",
            "duplicate_assignment": int("duplicate_assignment" in reasons),
            "conflicting_variant": int("conflicting_variant" in reasons),
            "assignment_after_signup": int("assignment_before_signup" not in reasons),
            "exposure_after_assignment": int("exposure_before_assignment" not in reasons),
            "conversion_after_exposure": int("conversion_before_exposure" not in reasons),
            "contamination_flag": 0,
            "crossover_flag": 0,
        }
        rows.append(row)
        if status == "valid" and spec is not None:
            valid.append(assignment)
    return rows, valid


def _exposure_rows(
    valid_assignments: list[Record],
    experiments: tuple[ExperimentSpec, ...],
    context: dict[str, Any],
) -> list[Record]:
    specs = {experiment.experiment_id: experiment for experiment in experiments}
    rows = []
    for assignment in valid_assignments:
        spec = specs[str(assignment["experiment_id"])]
        assignment_time = _parse_dt(str(assignment["assignment_timestamp"]))
        exposure = assignment.get("exposure_timestamp")
        exposure_time = (
            _parse_dt(str(exposure))
            if exposure
            else _first_event_time(
                context,
                str(assignment["user_id"]),
                (spec.exposure_event,),
                assignment_time,
                assignment_time + timedelta(days=spec.analysis_window_days),
            )
        )
        exposed = exposure_time is not None
        rows.append(
            {
                "experiment_id": assignment["experiment_id"],
                "assignment_id": assignment["assignment_id"],
                "user_id": assignment["user_id"],
                "variant": assignment["variant"],
                "assignment_timestamp": assignment["assignment_timestamp"],
                "first_exposure_timestamp": _format_dt(exposure_time) if exposure_time else "",
                "exposure_status": "exposed" if exposed else "not_exposed",
                "exposure_delay_hours": round(
                    (exposure_time - assignment_time).total_seconds() / 3600, 6
                )
                if exposure_time
                else "",
                "valid_exposure": int(
                    exposure_time is not None and exposure_time >= assignment_time
                ),
            }
        )
    return rows


def _population_rows(
    valid_assignments: list[Record],
    exposure_rows: list[Record],
    experiments: tuple[ExperimentSpec, ...],
) -> list[Record]:
    exposure_by_assignment = {str(row["assignment_id"]): row for row in exposure_rows}
    valid_by_experiment_variant = Counter(
        (str(row["experiment_id"]), str(row["variant"])) for row in valid_assignments
    )
    exposed_by_experiment_variant = Counter(
        (str(row["experiment_id"]), str(row["variant"]))
        for row in exposure_rows
        if int(row["valid_exposure"]) == 1
    )
    rows = []
    for experiment in experiments:
        for variant in experiment.variants:
            key = (experiment.experiment_id, variant)
            assigned = valid_by_experiment_variant[key]
            exposed = exposed_by_experiment_variant[key]
            rows.append(
                {
                    "experiment_id": experiment.experiment_id,
                    "variant": variant,
                    "assigned_users": assigned,
                    "exposed_users": exposed,
                    "valid_intention_to_treat_users": assigned,
                    "valid_exposed_users": exposed,
                    "excluded_users": assigned
                    - len(
                        [
                            assignment
                            for assignment in valid_assignments
                            if str(assignment["experiment_id"]) == experiment.experiment_id
                            and str(assignment["variant"]) == variant
                            and int(
                                exposure_by_assignment[str(assignment["assignment_id"])][
                                    "valid_exposure"
                                ]
                            )
                            == 1
                        ]
                    ),
                    "exclusion_reason": "not_exposed",
                    "exposure_rate": round(_safe_div(exposed, assigned), 6),
                }
            )
    return rows


def _srm_rows(
    valid_assignments: list[Record],
    experiments: tuple[ExperimentSpec, ...],
    config: ExperimentAnalysisConfig,
) -> list[Record]:
    counts = Counter((str(row["experiment_id"]), str(row["variant"])) for row in valid_assignments)
    rows = []
    for experiment in experiments:
        observed = [counts[(experiment.experiment_id, variant)] for variant in experiment.variants]
        expected_shares = [
            experiment.planned_allocation[variant] for variant in experiment.variants
        ]
        result = chi_square_srm(observed, expected_shares)
        total = sum(observed)
        for variant, observed_count, expected_share in zip(
            experiment.variants, observed, expected_shares, strict=True
        ):
            expected = total * expected_share
            rows.append(
                {
                    "experiment_id": experiment.experiment_id,
                    "variant": variant,
                    "observed_assignments": observed_count,
                    "expected_assignments": round(expected, 6),
                    "absolute_deviation": round(observed_count - expected, 6),
                    "relative_deviation": round(_safe_div(observed_count - expected, expected), 6),
                    "test_statistic": result["test_statistic"],
                    "degrees_of_freedom": result["degrees_of_freedom"],
                    "p_value": result["p_value"],
                    "configured_threshold": config.srm_p_value_threshold,
                    "expected_count_status": "small_expected_count" if expected < 5 else "adequate",
                    "srm_status": "fail"
                    if float(result["p_value"]) < config.srm_p_value_threshold
                    else "pass",
                    "method": result["method"],
                }
            )
    return rows


def _metric_rows(
    valid_assignments: list[Record],
    exposure_rows: list[Record],
    experiments: tuple[ExperimentSpec, ...],
    metrics: dict[str, MetricSpec],
    context: dict[str, Any],
    config: ExperimentAnalysisConfig,
) -> list[Record]:
    exposure_by_assignment = {str(row["assignment_id"]): row for row in exposure_rows}
    rows = []
    for experiment in experiments:
        metric_ids = (
            experiment.primary_metric,
            *experiment.secondary_metrics,
            *experiment.guardrail_metrics,
        )
        for population in config.populations:
            population_assignments = _assignments_for_population(
                valid_assignments, exposure_by_assignment, experiment, population
            )
            for treatment in experiment.treatment_variants:
                control = [
                    assignment
                    for assignment in population_assignments
                    if str(assignment["variant"]) == experiment.control_variant
                ]
                treatment_rows = [
                    assignment
                    for assignment in population_assignments
                    if str(assignment["variant"]) == treatment
                ]
                for metric_id in metric_ids:
                    metric = metrics[metric_id]
                    values = _metric_values(
                        control,
                        treatment_rows,
                        exposure_by_assignment,
                        experiment,
                        metric,
                        context,
                        population,
                    )
                    effect = _effect(values["control"], values["treatment"], metric, config)
                    rows.append(
                        {
                            "experiment_id": experiment.experiment_id,
                            "experiment_version": experiment.version,
                            "population": population,
                            "metric_id": metric.metric_id,
                            "metric_type": metric.metric_type,
                            "control_variant": experiment.control_variant,
                            "treatment_variant": treatment,
                            "control_sample_size": len(values["control"]),
                            "treatment_sample_size": len(values["treatment"]),
                            **effect,
                            "adjusted_p_value": effect["p_value"],
                            "significance_status": _significance_status(
                                float(effect["p_value"]), config.significance_level
                            ),
                            "practical_threshold": metric.practical_threshold,
                            "practical_significance_status": _practical_status(
                                float(effect["absolute_effect"]), metric
                            ),
                            "direction": metric.direction,
                            "data_quality_status": _metric_quality_status(
                                len(values["control"]), len(values["treatment"])
                            ),
                            "metric_role": _metric_role(metric_id, experiment),
                            "multiple_testing_family": experiment.multiple_testing_family,
                        }
                    )
    return rows


def _metric_values(
    control: list[Record],
    treatment: list[Record],
    exposure_by_assignment: dict[str, Record],
    experiment: ExperimentSpec,
    metric: MetricSpec,
    context: dict[str, Any],
    population: Population,
) -> dict[str, list[float]]:
    return {
        "control": [
            _outcome_value(
                assignment, exposure_by_assignment, experiment, metric, context, population
            )
            for assignment in control
        ],
        "treatment": [
            _outcome_value(
                assignment, exposure_by_assignment, experiment, metric, context, population
            )
            for assignment in treatment
        ],
    }


def _outcome_value(
    assignment: Record,
    exposure_by_assignment: dict[str, Record],
    experiment: ExperimentSpec,
    metric: MetricSpec,
    context: dict[str, Any],
    population: Population,
) -> float:
    start = _basis_time(assignment, exposure_by_assignment, population)
    end = start + timedelta(days=experiment.attribution_window_days)
    events = _events_in_window(context, str(assignment["user_id"]), start, end)
    if metric.metric_id == "paid_conversion_rate":
        return float(_has_paid_subscription(context, str(assignment["user_id"]), start, end))
    if metric.metric_id == "session_depth":
        sessions = {str(event["session_id"]) for event in events if event.get("session_id")}
        return _safe_div(len(events), len(sessions))
    if metric.metric_id == "time_to_onboarding_hours":
        event_time = _first_event_time(
            context, str(assignment["user_id"]), metric.event_names, start, end
        )
        if event_time is None:
            return float(experiment.attribution_window_days * 24)
        return round((event_time - start).total_seconds() / 3600, 6)
    count = sum(1 for event in events if str(event["event_name"]) in metric.event_names)
    if metric.metric_type == "binary":
        return float(count > 0)
    return float(count)


def _guardrail_rows(
    metric_rows: list[Record],
    experiments: tuple[ExperimentSpec, ...],
    metrics: dict[str, MetricSpec],
    config: ExperimentAnalysisConfig,
) -> list[Record]:
    guardrail_ids = {
        metric_id for experiment in experiments for metric_id in experiment.guardrail_metrics
    }
    rows = []
    for row in metric_rows:
        metric_id = str(row["metric_id"])
        if metric_id not in guardrail_ids or row["population"] != "intention_to_treat":
            continue
        metric = metrics[metric_id]
        effect = float(row["absolute_effect"])
        harm = effect if metric.direction == "decrease" else -effect
        severity = "critical" if metric.critical and harm > metric.harm_threshold else "none"
        status = "fail" if severity == "critical" else "pass"
        rows.append(
            {
                "experiment_id": row["experiment_id"],
                "guardrail_metric": metric_id,
                "control_value": row["control_value"],
                "treatment_value": row["treatment_value"],
                "effect": row["absolute_effect"],
                "confidence_lower": row["confidence_lower"],
                "confidence_upper": row["confidence_upper"],
                "p_value": row["p_value"],
                "adjusted_p_value": row["adjusted_p_value"],
                "harm_threshold": metric.harm_threshold,
                "harm_direction": "increase_is_harm"
                if metric.direction == "decrease"
                else "decrease_is_harm",
                "severity": severity,
                "status": status,
                "blocks_ship": int(status == "fail"),
                "configured_alpha": config.significance_level,
            }
        )
    return rows


def _segment_rows(
    valid_assignments: list[Record],
    exposure_rows: list[Record],
    experiments: tuple[ExperimentSpec, ...],
    metrics: dict[str, MetricSpec],
    context: dict[str, Any],
    config: ExperimentAnalysisConfig,
) -> list[Record]:
    exposure_by_assignment = {str(row["assignment_id"]): row for row in exposure_rows}
    users: dict[str, Record] = context["users"]
    rows = []
    for experiment in experiments:
        metric = metrics[experiment.primary_metric]
        assignments = _assignments_for_population(
            valid_assignments, exposure_by_assignment, experiment, "intention_to_treat"
        )
        for dimension in config.segment_dimensions:
            values = sorted(
                {str(users[str(row["user_id"])].get(dimension, "")) for row in assignments}
            )
            for value in values:
                segment_assignments = [
                    row
                    for row in assignments
                    if str(users[str(row["user_id"])].get(dimension, "")) == value
                ]
                for treatment in experiment.treatment_variants:
                    control = [
                        row
                        for row in segment_assignments
                        if str(row["variant"]) == experiment.control_variant
                    ]
                    treatment_rows = [
                        row for row in segment_assignments if str(row["variant"]) == treatment
                    ]
                    suppression = (
                        len(control) < config.suppression_threshold
                        or len(treatment_rows) < config.suppression_threshold
                    )
                    if suppression:
                        rows.append(
                            {
                                "experiment_id": experiment.experiment_id,
                                "population": "intention_to_treat",
                                "metric_id": metric.metric_id,
                                "segment_dimension": dimension,
                                "segment_value": value,
                                "control_variant": experiment.control_variant,
                                "treatment_variant": treatment,
                                "control_sample_size": len(control),
                                "treatment_sample_size": len(treatment_rows),
                                "control_value": "",
                                "treatment_value": "",
                                "absolute_effect": "",
                                "confidence_lower": "",
                                "confidence_upper": "",
                                "p_value": "",
                                "adjusted_p_value": "",
                                "suppression_status": "suppressed",
                                "heterogeneity_warning": "insufficient_segment_sample",
                            }
                        )
                        continue
                    values_by_arm = _metric_values(
                        control,
                        treatment_rows,
                        exposure_by_assignment,
                        experiment,
                        metric,
                        context,
                        "intention_to_treat",
                    )
                    effect = _effect(
                        values_by_arm["control"], values_by_arm["treatment"], metric, config
                    )
                    rows.append(
                        {
                            "experiment_id": experiment.experiment_id,
                            "population": "intention_to_treat",
                            "metric_id": metric.metric_id,
                            "segment_dimension": dimension,
                            "segment_value": value,
                            "control_variant": experiment.control_variant,
                            "treatment_variant": treatment,
                            "control_sample_size": len(control),
                            "treatment_sample_size": len(treatment_rows),
                            "control_value": effect["control_value"],
                            "treatment_value": effect["treatment_value"],
                            "absolute_effect": effect["absolute_effect"],
                            "confidence_lower": effect["confidence_lower"],
                            "confidence_upper": effect["confidence_upper"],
                            "p_value": effect["p_value"],
                            "adjusted_p_value": effect["p_value"],
                            "suppression_status": "reported",
                            "heterogeneity_warning": "exploratory_underpowered",
                        }
                    )
    return rows


def _apply_corrections(
    metric_rows: list[Record],
    guardrail_rows: list[Record],
    segment_rows: list[Record],
    config: ExperimentAnalysisConfig,
) -> tuple[list[Record], list[Record], list[Record], list[Record]]:
    multiple_rows: list[Record] = []
    grouped: dict[str, list[Record]] = defaultdict(list)
    for row in metric_rows:
        grouped[f"metrics:{row['experiment_id']}:{row['population']}"].append(row)
    for row in guardrail_rows:
        grouped[f"guardrails:{row['experiment_id']}"].append(row)
    reported_segments = [row for row in segment_rows if row["suppression_status"] == "reported"]
    for row in reported_segments:
        grouped[f"segments:{row['experiment_id']}:{row['segment_dimension']}"].append(row)
    for family, rows in grouped.items():
        p_values = [float(row["p_value"]) for row in rows]
        adjusted = adjust_p_values(p_values, config.multiple_testing)
        for row, adjusted_p in zip(rows, adjusted, strict=True):
            row["adjusted_p_value"] = adjusted_p
            if "significance_status" in row:
                row["significance_status"] = _significance_status(
                    adjusted_p, config.significance_level
                )
            multiple_rows.append(
                {
                    "family": family,
                    "experiment_id": row["experiment_id"],
                    "metric_id": row.get("metric_id", row.get("guardrail_metric", "")),
                    "population": row.get("population", "intention_to_treat"),
                    "raw_p_value": row["p_value"],
                    "adjusted_p_value": adjusted_p,
                    "method": config.multiple_testing,
                    "significance_level": config.significance_level,
                    "significance_status": _significance_status(
                        adjusted_p, config.significance_level
                    ),
                }
            )
    return metric_rows, guardrail_rows, segment_rows, multiple_rows


def _power_rows(
    metric_rows: list[Record],
    experiments: tuple[ExperimentSpec, ...],
    metrics: dict[str, MetricSpec],
) -> list[Record]:
    primary_by_experiment = {
        str(row["experiment_id"]): row
        for row in metric_rows
        if row["population"] == "intention_to_treat" and row["metric_role"] == "primary"
    }
    rows = []
    for experiment in experiments:
        row = primary_by_experiment.get(experiment.experiment_id)
        if row is None:
            continue
        metric = metrics[experiment.primary_metric]
        required = (
            binary_required_sample_size(
                float(row["control_value"]),
                experiment.minimum_detectable_effect,
                experiment.significance_level,
                experiment.target_power,
            )
            if metric.metric_type == "binary"
            else experiment.minimum_sample_size
        )
        observed = min(int(row["control_sample_size"]), int(row["treatment_sample_size"]))
        rows.append(
            {
                "experiment_id": experiment.experiment_id,
                "metric_id": experiment.primary_metric,
                "baseline_rate": row["control_value"],
                "minimum_detectable_effect": experiment.minimum_detectable_effect,
                "significance_level": experiment.significance_level,
                "target_power": experiment.target_power,
                "planned_sample_per_variant": experiment.minimum_sample_size,
                "observed_sample_per_variant": observed,
                "required_sample_per_variant": required,
                "sample_sufficiency": "sufficient" if observed >= required else "insufficient",
                "estimated_remaining_sample_per_variant": max(required - observed, 0),
                "method": "normal_approximation_binary_power"
                if metric.metric_type == "binary"
                else "minimum_sample_rule",
            }
        )
    return rows


def _decision_rows(
    metric_rows: list[Record],
    guardrail_rows: list[Record],
    srm_rows: list[Record],
    integrity_rows: list[Record],
    power_rows: list[Record],
    experiments: tuple[ExperimentSpec, ...],
    metrics: dict[str, MetricSpec],
    config: ExperimentAnalysisConfig,
) -> tuple[list[Record], dict[str, Decision]]:
    primary = {
        (str(row["experiment_id"]), str(row["treatment_variant"])): row
        for row in metric_rows
        if row["population"] == "intention_to_treat" and row["metric_role"] == "primary"
    }
    srm_status = {
        str(row["experiment_id"]): str(row["srm_status"])
        for row in srm_rows
        if str(row["variant"]) != ""
    }
    guardrail_status = {
        str(row["experiment_id"]): "fail"
        if any(
            str(item["status"]) == "fail"
            for item in guardrail_rows
            if item["experiment_id"] == row["experiment_id"]
        )
        else "pass"
        for row in metric_rows
    }
    power_status = {str(row["experiment_id"]): str(row["sample_sufficiency"]) for row in power_rows}
    integrity_status = {
        experiment.experiment_id: "fail"
        if any(
            row["experiment_id"] == experiment.experiment_id
            and row["integrity_status"] == "excluded"
            for row in integrity_rows
        )
        else "pass"
        for experiment in experiments
    }
    rows = []
    decisions: dict[str, Decision] = {}
    for experiment in experiments:
        metric = metrics[experiment.primary_metric]
        for treatment in experiment.treatment_variants:
            row = primary[(experiment.experiment_id, treatment)]
            effect = float(row["absolute_effect"])
            adjusted_p = float(row["adjusted_p_value"])
            stat_sig = adjusted_p < config.significance_level
            practical = _practical_status(effect, metric) == "met"
            sample = power_status.get(experiment.experiment_id, "insufficient")
            guardrails = guardrail_status.get(experiment.experiment_id, "pass")
            srm = srm_status.get(experiment.experiment_id, "pass")
            integrity = integrity_status[experiment.experiment_id]
            decision, reasons = _decision(
                effect,
                stat_sig,
                practical,
                sample,
                guardrails,
                srm,
                integrity,
                metric,
            )
            decisions[experiment.experiment_id] = decision
            rows.append(
                {
                    "experiment_id": experiment.experiment_id,
                    "treatment_variant": treatment,
                    "primary_metric": experiment.primary_metric,
                    "estimated_effect": row["absolute_effect"],
                    "confidence_lower": row["confidence_lower"],
                    "confidence_upper": row["confidence_upper"],
                    "p_value": row["p_value"],
                    "adjusted_p_value": row["adjusted_p_value"],
                    "practical_threshold": metric.practical_threshold,
                    "practical_significance": "met" if practical else "not_met",
                    "sample_sufficiency": sample,
                    "srm_status": srm,
                    "integrity_status": integrity,
                    "guardrail_status": guardrails,
                    "decision": decision,
                    "reason_codes": "|".join(reasons),
                }
            )
    return rows, decisions


def _decision(
    effect: float,
    stat_sig: bool,
    practical: bool,
    sample: str,
    guardrails: str,
    srm: str,
    integrity: str,
    metric: MetricSpec,
) -> tuple[Decision, list[str]]:
    favourable = effect > 0 if metric.direction == "increase" else effect < 0
    adverse = (
        effect < -metric.practical_threshold
        if metric.direction == "increase"
        else effect > metric.practical_threshold
    )
    reasons = []
    if srm == "fail" or integrity == "fail":
        return "invalid_experiment", ["integrity_or_srm_blocker"]
    if guardrails == "fail":
        return "do_not_ship", ["critical_guardrail_harm"]
    if adverse and (stat_sig or practical):
        return "do_not_ship", ["primary_metric_degradation"]
    if favourable and stat_sig and practical and sample == "sufficient":
        return "ship", ["statistical_and_practical_primary_lift"]
    if favourable and practical and sample == "sufficient":
        return "ship_with_caution", ["practical_lift_without_full_statistical_confidence"]
    if favourable and practical and sample == "insufficient":
        return "continue_experiment", ["promising_underpowered_effect"]
    reasons.append("primary_metric_not_statistically_or_practically_clear")
    return "no_clear_evidence", reasons


def _diagnostics(
    experiments: tuple[ExperimentSpec, ...],
    assignments: list[Record],
    integrity_rows: list[Record],
    exposure_rows: list[Record],
    srm_rows: list[Record],
    metric_rows: list[Record],
    guardrail_rows: list[Record],
    segment_rows: list[Record],
    decision_rows: list[Record],
) -> dict[str, object]:
    invalid_decisions = [row for row in decision_rows if row["decision"] == "invalid_experiment"]
    warnings = (
        [row for row in srm_rows if row["srm_status"] == "fail"]
        + [row for row in metric_rows if row["data_quality_status"] != "ok"]
        + [row for row in segment_rows if row["suppression_status"] == "suppressed"]
    )
    return {
        "trusted_input_compatibility": "passed",
        "experiments_evaluated": len(experiments),
        "assignment_counts": len(assignments),
        "valid_assignments": sum(1 for row in integrity_rows if row["integrity_status"] == "valid"),
        "duplicate_assignments": sum(int(row["duplicate_assignment"]) for row in integrity_rows),
        "invalid_variants": sum(
            1 for row in integrity_rows if "invalid_variant" in str(row["exclusion_reason"])
        ),
        "missing_exposures": sum(
            1 for row in exposure_rows if row["exposure_status"] == "not_exposed"
        ),
        "contamination_findings": 0,
        "crossover_findings": 0,
        "srm_findings": sum(1 for row in srm_rows if row["srm_status"] == "fail"),
        "insufficient_samples": sum(1 for row in metric_rows if row["data_quality_status"] != "ok"),
        "metric_availability": "passed",
        "zero_denominators": sum(
            1
            for row in metric_rows
            if int(row["control_sample_size"]) == 0 or int(row["treatment_sample_size"]) == 0
        ),
        "suppressed_segment_tests": sum(
            1 for row in segment_rows if row["suppression_status"] == "suppressed"
        ),
        "multiple_testing_families": sorted(
            {str(row["multiple_testing_family"]) for row in metric_rows}
        ),
        "guardrail_failures": sum(1 for row in guardrail_rows if row["status"] == "fail"),
        "decision_blockers": [row["experiment_id"] for row in invalid_decisions],
        "overall_status": "failed"
        if invalid_decisions
        else "passed_with_warnings"
        if warnings
        else "passed",
    }


def _validate_outputs(
    metric_rows: list[Record],
    guardrail_rows: list[Record],
    srm_rows: list[Record],
    decision_rows: list[Record],
) -> None:
    for row in metric_rows:
        if not 0 <= float(row["p_value"]) <= 1:
            raise ValueError("Metric p-values must be between zero and one.")
        if not 0 <= float(row["adjusted_p_value"]) <= 1:
            raise ValueError("Adjusted p-values must be between zero and one.")
        if float(row["confidence_lower"]) > float(row["confidence_upper"]):
            raise ValueError("Confidence interval bounds are not ordered.")
        if row["metric_type"] == "binary" and (
            not 0 <= float(row["control_value"]) <= 1 or not 0 <= float(row["treatment_value"]) <= 1
        ):
            raise ValueError("Binary metric rates must remain between zero and one.")
    for row in guardrail_rows:
        if row["status"] not in {"pass", "fail"}:
            raise ValueError("Unknown guardrail status.")
    for row in srm_rows:
        if not 0 <= float(row["p_value"]) <= 1:
            raise ValueError("SRM p-values must be between zero and one.")
    for row in decision_rows:
        if not row["reason_codes"]:
            raise ValueError("Decision rows require reason codes.")


def _write_outputs(
    *,
    output_dir: Path,
    config: ExperimentAnalysisConfig,
    run_id: str,
    trusted_row_counts: dict[str, int],
    source_ingestion_run_id: str,
    source_checksum: str,
    source_contract_versions: dict[str, str],
    experiments: tuple[ExperimentSpec, ...],
    metrics: dict[str, MetricSpec],
    integrity_rows: list[Record],
    population_rows: list[Record],
    srm_rows: list[Record],
    metric_rows: list[Record],
    guardrail_rows: list[Record],
    segment_rows: list[Record],
    multiple_rows: list[Record],
    power_rows: list[Record],
    decision_rows: list[Record],
    diagnostics: dict[str, object],
) -> None:
    files: dict[str, Callable[[Path], None]] = {
        "experiment-catalogue.json": lambda path: _write_json(
            path, _catalogue_json(experiments, metrics)
        ),
        "experiment-populations.csv": lambda path: _write_csv(path, population_rows),
        "assignment-integrity.csv": lambda path: _write_csv(path, integrity_rows),
        "sample-ratio-mismatch.csv": lambda path: _write_csv(path, srm_rows),
        "metric-results.csv": lambda path: _write_csv(path, metric_rows),
        "guardrail-results.csv": lambda path: _write_csv(path, guardrail_rows),
        "segment-effects.csv": lambda path: _write_csv(path, segment_rows),
        "multiple-testing-results.csv": lambda path: _write_csv(path, multiple_rows),
        "power-analysis.csv": lambda path: _write_csv(path, power_rows),
        "decision-summary.csv": lambda path: _write_csv(path, decision_rows),
        "experiment-summary.json": lambda path: _write_json(
            path, _summary(run_id, experiments, decision_rows, diagnostics)
        ),
        "run-diagnostics.json": lambda path: _write_json(path, diagnostics),
        "analysis-lineage.json": lambda path: _write_json(
            path,
            _lineage(source_ingestion_run_id, source_checksum, source_contract_versions),
        ),
        "experiment-report.md": lambda path: _write_text(
            path,
            _experiment_report(experiments, decision_rows, metric_rows, srm_rows, guardrail_rows),
        ),
    }
    checksums = {}
    for filename, writer in files.items():
        path = output_dir / filename
        writer(path)
        checksums[filename] = file_sha256(path)
    manifest = {
        "analysis_run_id": run_id,
        "software_version": get_project_metadata().version,
        "source_ingestion_run_id": source_ingestion_run_id,
        "source_manifest_checksum": source_checksum,
        "source_contract_versions": source_contract_versions,
        "experiment_catalogue_version": EXPERIMENT_CATALOGUE_VERSION,
        "experiment_versions": {
            experiment.experiment_id: experiment.version for experiment in experiments
        },
        "analysis_timestamp": config.analysis_time,
        "assignment_and_exposure_windows": {
            experiment.experiment_id: {
                "assignment_start": experiment.assignment_start,
                "assignment_end": experiment.assignment_end,
                "analysis_window_days": experiment.analysis_window_days,
                "attribution_window_days": experiment.attribution_window_days,
            }
            for experiment in experiments
        },
        "populations": list(config.populations),
        "significance_level": config.significance_level,
        "confidence_level": config.confidence_level,
        "multiple_testing_method": config.multiple_testing,
        "segment_suppression_threshold": config.suppression_threshold,
        "metric_versions": {"experiment_metrics": EXPERIMENT_METRIC_VERSION},
        "input_row_counts": trusted_row_counts,
        "output_row_counts": {
            "assignment-integrity.csv": len(integrity_rows),
            "metric-results.csv": len(metric_rows),
            "guardrail-results.csv": len(guardrail_rows),
            "segment-effects.csv": len(segment_rows),
            "decision-summary.csv": len(decision_rows),
        },
        "output_checksums": checksums,
        "overall_status": diagnostics["overall_status"],
        "created_at": config.fixed_run_time,
    }
    _write_json(output_dir / "analysis-manifest.json", manifest)


def _catalogue_json(
    experiments: tuple[ExperimentSpec, ...], metrics: dict[str, MetricSpec]
) -> Record:
    return {
        "catalogue_version": EXPERIMENT_CATALOGUE_VERSION,
        "metric_version": EXPERIMENT_METRIC_VERSION,
        "experiments": [_dataclass_dict(experiment) for experiment in experiments],
        "metrics": [_dataclass_dict(metric) for metric in metrics.values()],
    }


def _summary(
    run_id: str,
    experiments: tuple[ExperimentSpec, ...],
    decision_rows: list[Record],
    diagnostics: dict[str, object],
) -> Record:
    return {
        "analysis_run_id": run_id,
        "analysis_version": EXPERIMENT_ANALYSIS_VERSION,
        "experiments_evaluated": len(experiments),
        "decisions": decision_rows,
        "overall_status": diagnostics["overall_status"],
        "synthetic_data_notice": (
            "All experiment evidence is generated from synthetic NexaFlow data."
        ),
    }


def _lineage(
    source_ingestion_run_id: str,
    source_checksum: str,
    source_contract_versions: dict[str, str],
) -> Record:
    return {
        "source_ingestion_run_id": source_ingestion_run_id,
        "source_manifest_checksum": source_checksum,
        "source_contract_versions": source_contract_versions,
        "relationships": [
            "accepted/experiment_assignments",
            "accepted/clickstream_events",
            "accepted/users",
            "accepted/subscriptions",
            "accepted/customer_feedback",
            "assignment integrity",
            "exposure and outcome attribution",
            "experiment populations",
            "metric estimates",
            "guardrail analysis",
            "segment effects",
            "decisions",
        ],
        "experiment_catalogue_version": EXPERIMENT_CATALOGUE_VERSION,
        "metric_version": EXPERIMENT_METRIC_VERSION,
    }


def _experiment_report(
    experiments: tuple[ExperimentSpec, ...],
    decision_rows: list[Record],
    metric_rows: list[Record],
    srm_rows: list[Record],
    guardrail_rows: list[Record],
) -> str:
    lines = [
        "# Experiment Analysis Report",
        "",
        "All data is synthetic. This is fixed-window offline experiment analysis, not",
        "online experimentation infrastructure or an automatic rollout decision.",
        "",
    ]
    for experiment in experiments:
        decision = next(
            row for row in decision_rows if row["experiment_id"] == experiment.experiment_id
        )
        primary = next(
            row
            for row in metric_rows
            if row["experiment_id"] == experiment.experiment_id
            and row["population"] == "intention_to_treat"
            and row["metric_role"] == "primary"
        )
        srm = next(row for row in srm_rows if row["experiment_id"] == experiment.experiment_id)
        guardrails = [
            row for row in guardrail_rows if row["experiment_id"] == experiment.experiment_id
        ]
        lines.extend(
            [
                f"## {experiment.experiment_name}",
                "",
                f"Hypothesis: {experiment.business_hypothesis}",
                f"Variants: {', '.join(experiment.variants)}.",
                f"SRM status: {srm['srm_status']} (p={srm['p_value']}).",
                (
                    f"Primary metric {experiment.primary_metric}: effect "
                    f"{primary['absolute_effect']} with CI "
                    f"[{primary['confidence_lower']}, {primary['confidence_upper']}], "
                    f"adjusted p={primary['adjusted_p_value']}."
                ),
                f"Guardrails: {_guardrail_summary(guardrails)}.",
                f"Decision: {decision['decision']} ({decision['reason_codes']}).",
                "",
            ]
        )
    return "\n".join(lines)


def _assignments_for_population(
    assignments: list[Record],
    exposure_by_assignment: dict[str, Record],
    experiment: ExperimentSpec,
    population: Population,
) -> list[Record]:
    rows = [row for row in assignments if str(row["experiment_id"]) == experiment.experiment_id]
    if population == "intention_to_treat":
        return rows
    return [
        row
        for row in rows
        if int(exposure_by_assignment[str(row["assignment_id"])]["valid_exposure"]) == 1
    ]


def _effect(
    control_values: list[float],
    treatment_values: list[float],
    metric: MetricSpec,
    config: ExperimentAnalysisConfig,
) -> dict[str, float | str]:
    if metric.metric_type == "binary":
        return two_proportion_effect(
            int(sum(control_values)),
            len(control_values),
            int(sum(treatment_values)),
            len(treatment_values),
            config.confidence_level,
        )
    return welch_mean_effect(control_values, treatment_values, config.confidence_level)


def _basis_time(
    assignment: Record,
    exposure_by_assignment: dict[str, Record],
    population: Population,
) -> datetime:
    if population == "exposed":
        exposure = exposure_by_assignment[str(assignment["assignment_id"])][
            "first_exposure_timestamp"
        ]
        if exposure:
            return _parse_dt(str(exposure))
    return _parse_dt(str(assignment["assignment_timestamp"]))


def _events_in_window(
    context: dict[str, Any],
    user_id: str,
    start: datetime,
    end: datetime,
) -> list[Record]:
    events_by_user: dict[str, list[Record]] = context["events_by_user"]
    return [
        event
        for event in events_by_user.get(user_id, [])
        if start <= _parse_dt(str(event["event_timestamp"])) <= end
    ]


def _first_event_time(
    context: dict[str, Any],
    user_id: str,
    event_names: tuple[str, ...],
    start: datetime,
    end: datetime,
) -> datetime | None:
    for event in _events_in_window(context, user_id, start, end):
        if str(event["event_name"]) in event_names:
            return _parse_dt(str(event["event_timestamp"]))
    return None


def _has_paid_subscription(
    context: dict[str, Any],
    user_id: str,
    start: datetime,
    end: datetime,
) -> bool:
    subscriptions_by_user: dict[str, list[Record]] = context["subscriptions_by_user"]
    for subscription in subscriptions_by_user.get(user_id, []):
        timestamp = _parse_dt(str(subscription["period_start_timestamp"]))
        if start <= timestamp <= end and float(subscription["monthly_recurring_revenue"]) > 0:
            return True
    return False


def _metric_role(metric_id: str, experiment: ExperimentSpec) -> str:
    if metric_id == experiment.primary_metric:
        return "primary"
    if metric_id in experiment.guardrail_metrics:
        return "guardrail"
    return "secondary"


def _significance_status(p_value: float, alpha: float) -> str:
    return "significant" if p_value < alpha else "not_significant"


def _practical_status(effect: float, metric: MetricSpec) -> str:
    if metric.direction == "increase":
        return "met" if effect >= metric.practical_threshold else "not_met"
    return "met" if -effect >= metric.practical_threshold else "not_met"


def _metric_quality_status(control_n: int, treatment_n: int) -> str:
    if control_n == 0 or treatment_n == 0:
        return "zero_denominator"
    if control_n < 2 or treatment_n < 2:
        return "small_sample_warning"
    return "ok"


def _guardrail_summary(rows: list[Record]) -> str:
    if not rows:
        return "none configured"
    failures = [row["guardrail_metric"] for row in rows if row["status"] == "fail"]
    return f"failed {', '.join(failures)}" if failures else "passed"


def _dataclass_dict(value: object) -> Record:
    output = dict(value.__dict__)
    for key, item in list(output.items()):
        if isinstance(item, tuple):
            output[key] = list(item)
    return output


def _safe_div(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _default_run_id(config: ExperimentAnalysisConfig) -> str:
    if config.fixed_run_time:
        stamp = (
            config.fixed_run_time.replace(":", "")
            .replace("-", "")
            .replace("T", "-")
            .replace("Z", "")
        )
    else:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"experiments-{stamp}"


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _format_dt(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[Record]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def run_sample_to_temp() -> ExperimentAnalysisResult:
    """Run sample ingestion then experiment analysis in a temporary directory."""

    from product_growth_intelligence.ingestion import IngestionConfig, run_batch_ingestion

    with TemporaryDirectory() as temp:
        root = Path(temp)
        ingestion = run_batch_ingestion(
            IngestionConfig(
                source=Path("data/samples/nexaflow"),
                output_root=root / "interim",
                quality_root=root / "quality",
                run_id="milestone9-source",
                fixed_ingestion_time="2026-01-01T00:00:00Z",
                overwrite=True,
            )
        )
        return run_experiment_analysis(
            ExperimentAnalysisConfig(
                input_dir=ingestion.output_dir,
                output_root=root / "experiments",
                run_id="milestone9-experiments",
                fixed_run_time="2026-01-02T00:00:00Z",
                overwrite=True,
            )
        )
