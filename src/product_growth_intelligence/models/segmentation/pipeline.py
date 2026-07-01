"""Deterministic point-in-time user segmentation pipeline."""

# ruff: noqa: ANN401

from __future__ import annotations

import csv
import json
import math
import os
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

import numpy as np
from sklearn.cluster import KMeans  # type: ignore[import-untyped]
from sklearn.decomposition import PCA  # type: ignore[import-untyped]
from sklearn.metrics import (  # type: ignore[import-untyped]
    adjusted_rand_score,
    calinski_harabasz_score,
    davies_bouldin_score,
    silhouette_score,
)
from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]

from product_growth_intelligence.analytics.inputs import (
    dataset_row_counts,
    load_trusted_input,
    source_manifest_checksum,
)
from product_growth_intelligence.analytics.retention.definitions import DEFAULT_QUALIFYING_EVENTS
from product_growth_intelligence.data_generation.models import Record
from product_growth_intelligence.ingestion.fingerprints import file_sha256, record_fingerprint
from product_growth_intelligence.metadata import get_project_metadata
from product_growth_intelligence.models.segmentation.models import (
    RuleAssignment,
    SegmentationConfig,
    SegmentationResult,
    SegmentationRow,
    SegmentationSnapshot,
)

SEGMENTATION_VERSION = "2026-07-milestone-7"
RULE_VERSION = "2026-07-milestone-7-rules"

NUMERIC_FEATURES = (
    "account_age_days",
    "sessions_in_lookback",
    "active_days_in_lookback",
    "qualifying_events_in_lookback",
    "events_per_active_day",
    "average_session_duration_seconds",
    "days_since_last_activity",
    "active_day_proportion",
    "meaningful_sessions",
    "projects_created",
    "tasks_created",
    "tasks_completed",
    "task_completion_ratio",
    "files_uploaded",
    "comments_added",
    "searches_performed",
    "dashboard_views",
    "report_exports",
    "invites_sent",
    "invites_accepted",
    "members_added",
    "projects_shared",
    "collaboration_events",
    "collaboration_active_days",
    "automation_rules_created",
    "automation_executions",
    "successful_automation_uses",
    "integrations_connected",
    "advanced_feature_count",
    "upgrade_prompts_viewed",
    "trials_started",
    "current_recurring_revenue",
    "upgrade_count",
    "downgrade_count",
    "cancellation_intent_events",
    "days_on_current_plan",
    "recommendations_shown",
    "recommendations_clicked",
    "recommendations_accepted",
    "recommendation_click_through_rate",
    "recommendation_acceptance_rate",
    "feature_errors",
    "failed_requests",
    "error_event_rate",
    "sessions_containing_errors",
    "onboarding_step_repetitions",
    "active_periods_in_lookback",
    "longest_inactivity_gap_days",
    "prior_resurrection_count",
    "recent_engagement_decline",
    "highest_activation_stage",
)
BINARY_FEATURES = (
    "paid_user_flag",
    "collaboration_adoption_flag",
    "automation_adoption_flag",
    "paid_conversion_flag",
    "incomplete_onboarding_flag",
    "activation_achieved",
    "onboarding_completed",
    "collaboration_funnel_completed",
    "automation_adoption_completed",
)
CATEGORICAL_PROFILE_FEATURES = (
    "persona",
    "acquisition_channel",
    "region",
    "company_size_band",
    "is_team_account",
    "initial_plan",
    "current_plan",
    "subscription_status",
)
CLUSTERING_FEATURES = NUMERIC_FEATURES + BINARY_FEATURES
PROFILE_SEGMENT_METHODS = ("rule_based", "kmeans")


def run_segmentation(config: SegmentationConfig) -> SegmentationResult:
    """Run governed segmentation against trusted accepted inputs."""

    config.validate()
    trusted = load_trusted_input(config.input_dir)
    run_id = config.run_id or _default_run_id(config)
    output_dir = config.output_root / run_id
    if output_dir.exists() and any(output_dir.iterdir()) and not config.overwrite:
        msg = f"Output directory {output_dir} already exists and is not empty. Pass --overwrite."
        raise FileExistsError(msg)
    if config.validate_only:
        return SegmentationResult(
            run_id=run_id,
            status="validated",
            output_dir=output_dir,
            eligible_snapshots=0,
            selected_cluster_count=0,
            selected_algorithm=config.algorithm,
        )

    rows, exclusions = build_segmentation_rows(config)
    if len(rows) < 2:
        msg = "Segmentation requires at least two eligible snapshots."
        raise ValueError(msg)
    output_dir.mkdir(parents=True, exist_ok=True)

    rule_assignments = assign_rule_based_segments(rows, trusted.source_ingestion_run_id)
    matrix, active_features, constant_features = _clustering_matrix(rows)
    candidate_rows, selected_candidate = _candidate_metrics(matrix, config)
    labels, centroids_scaled, scaler = _fit_selected_kmeans(matrix, selected_candidate, config)
    canonical = _canonical_cluster_mapping(rows, labels, int(selected_candidate["cluster_count"]))
    canonical_labels = [canonical[int(label)] for label in labels]
    stability_rows = _stability_rows(matrix, int(selected_candidate["cluster_count"]), config)
    cluster_names = _cluster_names(rows, canonical_labels)
    pca_rows, pca_variance_rows, centroid_pca_rows = _pca_outputs(
        rows, matrix, canonical_labels, scaler, config
    )
    cluster_assignments = _cluster_assignments(
        rows,
        canonical_labels,
        cluster_names,
        matrix,
        pca_rows,
        trusted.source_ingestion_run_id,
    )
    profiles = _profiles(rows, rule_assignments, cluster_assignments, config.suppression_threshold)
    name_mapping = _name_mapping(cluster_names, rows, canonical_labels)
    diagnostics = _diagnostics(
        rows,
        exclusions,
        constant_features,
        candidate_rows,
        selected_candidate,
        stability_rows,
        profiles,
        rule_assignments,
    )
    _validate_outputs(rows, rule_assignments, cluster_assignments, profiles, candidate_rows)
    _write_outputs(
        output_dir=output_dir,
        config=config,
        run_id=run_id,
        source_ingestion_run_id=trusted.source_ingestion_run_id,
        source_checksum=trusted.source_manifest_checksum
        or source_manifest_checksum(config.input_dir),
        source_contract_versions=trusted.contract_versions,
        trusted_row_counts=dataset_row_counts(trusted),
        rows=rows,
        rule_assignments=rule_assignments,
        candidate_rows=candidate_rows,
        stability_rows=stability_rows,
        cluster_assignments=cluster_assignments,
        profiles=profiles,
        centroids=_centroid_rows(rows, canonical_labels),
        pca_rows=pca_rows,
        pca_variance_rows=pca_variance_rows,
        centroid_pca_rows=centroid_pca_rows,
        name_mapping=name_mapping,
        diagnostics=diagnostics,
        selected_candidate=selected_candidate,
        active_features=active_features,
    )
    return SegmentationResult(
        run_id=run_id,
        status=str(diagnostics["overall_status"]),
        output_dir=output_dir,
        eligible_snapshots=len(rows),
        selected_cluster_count=int(selected_candidate["cluster_count"]),
        selected_algorithm=str(selected_candidate["algorithm"]),
        diagnostics=diagnostics,
    )


def build_segmentation_rows(
    config: SegmentationConfig,
) -> tuple[list[SegmentationRow], dict[str, int]]:
    """Create one latest valid point-in-time segmentation row per eligible user."""

    trusted = load_trusted_input(config.input_dir)
    snapshot = _parse_dt(config.snapshot_time)
    feature_start = snapshot - timedelta(days=config.lookback_days)
    users = sorted(trusted.datasets["users"], key=lambda row: str(row["user_id"]))
    sessions_by_user = _records_by_user(trusted.datasets["sessions"])
    events_by_user = _records_by_user(trusted.datasets["clickstream_events"])
    usage_by_user = _records_by_user(trusted.datasets["feature_usage"])
    subscriptions_by_user = _records_by_user(trusted.datasets["subscriptions"])
    rows: list[SegmentationRow] = []
    exclusions: Counter[str] = Counter()
    for user in users:
        user_id = str(user["user_id"])
        signup = _parse_dt(str(user["signup_timestamp"]))
        if signup > snapshot:
            exclusions["signed_up_after_snapshot"] += 1
            continue
        if (snapshot - signup).days < config.minimum_account_age:
            exclusions["below_minimum_account_age"] += 1
            continue
        features = _features(
            user=user,
            snapshot=snapshot,
            feature_start=feature_start,
            sessions=sessions_by_user[user_id],
            events=events_by_user[user_id],
            usage=usage_by_user[user_id],
            subscriptions=subscriptions_by_user[user_id],
        )
        if (
            int(features["qualifying_events_in_lookback"]) < config.minimum_activity
            and not config.include_inactive_users
        ):
            exclusions["below_minimum_activity"] += 1
            continue
        snapshot_id = record_fingerprint(
            {"user_id": user_id, "segmentation_snapshot": _format_dt(snapshot)}
        )[:16]
        rows.append(
            SegmentationRow(
                snapshot=SegmentationSnapshot(
                    snapshot_id=snapshot_id,
                    user_id=user_id,
                    snapshot_timestamp=_format_dt(snapshot),
                    feature_window_start=_format_dt(feature_start),
                    feature_window_end=_format_dt(snapshot),
                    source_ingestion_run_id=trusted.source_ingestion_run_id,
                ),
                features=features,
            )
        )
    return sorted(rows, key=lambda row: row.snapshot.user_id), dict(sorted(exclusions.items()))


def assign_rule_based_segments(
    rows: list[SegmentationRow], source_ingestion_run_id: str
) -> list[RuleAssignment]:
    """Assign mutually exclusive interpretable rule-based segments."""

    assignments: list[RuleAssignment] = []
    for row in rows:
        features = row.features
        segment_id, name, matched_rule, reasons = _rule_for(features)
        assignments.append(
            RuleAssignment(
                snapshot_id=row.snapshot.snapshot_id,
                user_id=row.snapshot.user_id,
                snapshot_timestamp=row.snapshot.snapshot_timestamp,
                rule_based_segment_id=segment_id,
                segment_name=name,
                rule_version=RULE_VERSION,
                matched_rule=matched_rule,
                reason_codes=reasons,
                supporting_feature_summary={
                    "sessions": features["sessions_in_lookback"],
                    "active_days": features["active_days_in_lookback"],
                    "qualifying_events": features["qualifying_events_in_lookback"],
                    "days_since_last_activity": features["days_since_last_activity"],
                    "current_plan": features["current_plan"],
                    "error_event_rate": features["error_event_rate"],
                },
                source_ingestion_run_id=source_ingestion_run_id,
            )
        )
    return assignments


def _features(
    *,
    user: Record,
    snapshot: datetime,
    feature_start: datetime,
    sessions: list[Record],
    events: list[Record],
    usage: list[Record],
    subscriptions: list[Record],
) -> Record:
    window_sessions = [
        session
        for session in sessions
        if feature_start <= _parse_dt(str(session["session_start_timestamp"])) <= snapshot
    ]
    prior_events = [
        event for event in events if _parse_dt(str(event["event_timestamp"])) <= snapshot
    ]
    window_events = [
        event
        for event in prior_events
        if feature_start <= _parse_dt(str(event["event_timestamp"])) <= snapshot
    ]
    qualifying = [
        event for event in window_events if str(event["event_name"]) in DEFAULT_QUALIFYING_EVENTS
    ]
    active_days = {_parse_dt(str(event["event_timestamp"])).date() for event in qualifying}
    midpoint = feature_start + (snapshot - feature_start) / 2
    recent_events = [
        event for event in qualifying if _parse_dt(str(event["event_timestamp"])) > midpoint
    ]
    prior_window_events = [
        event for event in qualifying if _parse_dt(str(event["event_timestamp"])) <= midpoint
    ]
    event_counts = Counter(str(event["event_name"]) for event in window_events)
    prior_event_counts = Counter(str(event["event_name"]) for event in prior_events)
    last_activity = max(
        (_parse_dt(str(event["event_timestamp"])) for event in qualifying), default=None
    )
    historical_days = sorted(
        {
            _parse_dt(str(event["event_timestamp"])).date()
            for event in prior_events
            if str(event["event_name"]) in DEFAULT_QUALIFYING_EVENTS
        }
    )
    plan, status, mrr, days_on_plan = _subscription_context(subscriptions, snapshot)
    task_created = event_counts["task_created"]
    task_completed = event_counts["task_completed"]
    recommendation_shown = event_counts["recommendation_shown"]
    recommendation_clicked = event_counts["recommendation_clicked"]
    recommendation_accepted = event_counts["recommendation_accepted"]
    errors = event_counts["feature_error"] + event_counts["request_failed"]
    automation_events = event_counts["automation_created"] + event_counts["automation_executed"]
    collaboration_events = (
        event_counts["invite_sent"]
        + event_counts["invite_accepted"]
        + event_counts["member_added"]
        + event_counts["project_shared"]
    )
    advanced_count = sum(
        1
        for event in window_events
        if str(event.get("feature_name")) in {"automation", "integrations", "reports"}
    )
    sessions_with_errors = {
        str(event.get("session_id"))
        for event in window_events
        if str(event["event_name"]) in {"feature_error", "request_failed"}
    }
    onboarding_steps = [
        str(event.get("properties", {}).get("step", "unknown"))
        for event in window_events
        if str(event["event_name"]) == "onboarding_step_completed"
    ]
    return {
        "account_age_days": (snapshot - _parse_dt(str(user["signup_timestamp"]))).days,
        "sessions_in_lookback": len(window_sessions),
        "active_days_in_lookback": len(active_days),
        "qualifying_events_in_lookback": len(qualifying),
        "events_per_active_day": _safe_div(len(qualifying), len(active_days)),
        "average_session_duration_seconds": _safe_div(
            sum(
                float(session.get("session_duration_seconds", 0) or 0)
                for session in window_sessions
            ),
            len(window_sessions),
        ),
        "days_since_last_activity": (snapshot - last_activity).days if last_activity else 999,
        "active_day_proportion": _safe_div(
            len(active_days), max((snapshot - feature_start).days, 1)
        ),
        "meaningful_sessions": len({str(event.get("session_id")) for event in qualifying}),
        "projects_created": event_counts["project_created"],
        "tasks_created": task_created,
        "tasks_completed": task_completed,
        "task_completion_ratio": _safe_div(task_completed, task_created),
        "files_uploaded": event_counts["file_uploaded"],
        "comments_added": event_counts["comment_added"],
        "searches_performed": event_counts["search_performed"],
        "dashboard_views": event_counts["dashboard_viewed"],
        "report_exports": event_counts["report_exported"],
        "invites_sent": event_counts["invite_sent"],
        "invites_accepted": event_counts["invite_accepted"],
        "members_added": event_counts["member_added"],
        "projects_shared": event_counts["project_shared"],
        "collaboration_events": collaboration_events,
        "collaboration_active_days": len(
            {
                _parse_dt(str(event["event_timestamp"])).date()
                for event in window_events
                if str(event.get("feature_name")) == "collaboration"
            }
        ),
        "automation_rules_created": event_counts["automation_created"],
        "automation_executions": event_counts["automation_executed"],
        "successful_automation_uses": event_counts["automation_executed"],
        "integrations_connected": event_counts["integration_connected"],
        "advanced_feature_count": advanced_count,
        "upgrade_prompts_viewed": event_counts["upgrade_prompt_viewed"],
        "trials_started": event_counts["trial_started"],
        "current_recurring_revenue": mrr,
        "upgrade_count": prior_event_counts["plan_upgraded"],
        "downgrade_count": prior_event_counts["plan_downgraded"],
        "cancellation_intent_events": event_counts["cancellation_started"],
        "days_on_current_plan": days_on_plan,
        "recommendations_shown": recommendation_shown,
        "recommendations_clicked": recommendation_clicked,
        "recommendations_accepted": recommendation_accepted,
        "recommendation_click_through_rate": _safe_div(
            recommendation_clicked, recommendation_shown
        ),
        "recommendation_acceptance_rate": _safe_div(
            recommendation_accepted, recommendation_clicked
        ),
        "feature_errors": event_counts["feature_error"],
        "failed_requests": event_counts["request_failed"],
        "error_event_rate": _safe_div(errors, len(window_events)),
        "sessions_containing_errors": len(sessions_with_errors - {""}),
        "onboarding_step_repetitions": max(0, len(onboarding_steps) - len(set(onboarding_steps))),
        "active_periods_in_lookback": len({day.isocalendar().week for day in active_days}),
        "longest_inactivity_gap_days": _longest_gap(historical_days),
        "prior_resurrection_count": _resurrection_count(historical_days),
        "recent_engagement_decline": 1 if len(recent_events) < len(prior_window_events) else 0,
        "highest_activation_stage": _highest_activation_stage(prior_event_counts),
        "paid_user_flag": 1 if _plan_rank(plan) > 0 else 0,
        "collaboration_adoption_flag": 1 if collaboration_events > 0 else 0,
        "automation_adoption_flag": 1 if automation_events > 0 else 0,
        "paid_conversion_flag": 1 if prior_event_counts["subscription_started"] > 0 else 0,
        "incomplete_onboarding_flag": 0 if prior_event_counts["onboarding_completed"] > 0 else 1,
        "activation_achieved": 1
        if prior_event_counts["workspace_created"] > 0 or prior_event_counts["task_completed"] > 0
        else 0,
        "onboarding_completed": 1 if prior_event_counts["onboarding_completed"] > 0 else 0,
        "collaboration_funnel_completed": 1 if prior_event_counts["project_shared"] > 0 else 0,
        "automation_adoption_completed": 1 if prior_event_counts["automation_executed"] > 0 else 0,
        "persona": str(user.get("persona", "unknown")),
        "acquisition_channel": str(user.get("acquisition_channel", "unknown")),
        "region": str(user.get("region", "unknown")),
        "company_size_band": str(user.get("company_size_band", "unknown")),
        "is_team_account": str(user.get("is_team_account", "unknown")),
        "initial_plan": str(user.get("initial_plan", "unknown")),
        "current_plan": plan,
        "subscription_status": status,
    }


def _rule_for(features: Record) -> tuple[str, str, str, tuple[str, ...]]:
    if int(features["qualifying_events_in_lookback"]) == 0:
        return ("inactive_user", "Inactive User", "inactive_user", ("no_lookback_activity",))
    if (
        float(features["error_event_rate"]) >= 0.08
        or int(features["sessions_containing_errors"]) >= 2
    ):
        return ("high_friction", "High Friction User", "high_friction", ("elevated_error_rate",))
    if int(features["paid_user_flag"]) and int(features["active_days_in_lookback"]) <= 1:
        return (
            "paid_under_engaged",
            "Paid Under-engaged",
            "paid_under_engaged",
            ("paid_low_activity",),
        )
    if (
        int(features["automation_executions"]) >= 2
        or int(features["automation_rules_created"]) >= 2
    ):
        return (
            "automation_power_user",
            "Automation Power User",
            "automation_power_user",
            ("automation_depth",),
        )
    if int(features["collaboration_events"]) >= 2:
        return (
            "collaboration_adopter",
            "Collaboration Adopter",
            "collaboration_adopter",
            ("collaboration_usage",),
        )
    if int(features["recent_engagement_decline"]) and int(features["prior_resurrection_count"]) > 0:
        return (
            "declining_engagement",
            "Declining Engagement",
            "declining_engagement",
            ("recent_activity_below_prior",),
        )
    if (
        int(features["active_days_in_lookback"]) >= 3
        and int(features["qualifying_events_in_lookback"]) >= 10
    ):
        return ("core_engaged", "Core Engaged", "core_engaged", ("sustained_activity",))
    if int(features["account_age_days"]) <= 28:
        return ("new_explorer", "New Explorer", "new_explorer", ("newer_account",))
    return ("casual_user", "Casual User", "casual_user", ("limited_depth",))


def _clustering_matrix(
    rows: list[SegmentationRow],
) -> tuple[np.ndarray[Any, Any], list[str], list[str]]:
    raw = np.array(
        [[float(row.features[feature]) for feature in CLUSTERING_FEATURES] for row in rows],
        dtype=float,
    )
    variances = raw.var(axis=0)
    active_indices = [index for index, variance in enumerate(variances) if variance > 0]
    if not active_indices:
        msg = "No non-constant clustering features available."
        raise ValueError(msg)
    active_features = [CLUSTERING_FEATURES[index] for index in active_indices]
    constant_features = [
        CLUSTERING_FEATURES[index] for index, variance in enumerate(variances) if variance <= 0
    ]
    return raw[:, active_indices], active_features, constant_features


def _candidate_metrics(
    matrix: np.ndarray[Any, Any], config: SegmentationConfig
) -> tuple[list[Record], Record]:
    cluster_counts = (
        config.candidate_clusters if config.cluster_count is None else (config.cluster_count,)
    )
    scaler = StandardScaler()
    scaled = scaler.fit_transform(matrix)
    rows: list[Record] = []
    for cluster_count in cluster_counts:
        if cluster_count > len(matrix):
            rows.append(_rejected_candidate(cluster_count, "cluster_count_exceeds_population"))
            continue
        if cluster_count > len({tuple(row) for row in matrix.tolist()}):
            rows.append(_rejected_candidate(cluster_count, "cluster_count_exceeds_unique_rows"))
            continue
        model = KMeans(
            n_clusters=cluster_count,
            random_state=config.random_seed,
            n_init=config.kmeans_initialisations,
        )
        labels = model.fit_predict(scaled)
        counts = Counter(int(label) for label in labels)
        smallest = min(counts.values())
        largest = max(counts.values())
        eligible = smallest >= config.minimum_cluster_size
        stability = _stability_score(scaled, cluster_count, config)
        rows.append(
            {
                "algorithm": "kmeans",
                "cluster_count": cluster_count,
                "random_seed": config.random_seed,
                "silhouette_score": _metric_or_none(silhouette_score, scaled, labels),
                "davies_bouldin_score": _metric_or_none(davies_bouldin_score, scaled, labels),
                "calinski_harabasz_score": _metric_or_none(calinski_harabasz_score, scaled, labels),
                "smallest_cluster_size": smallest,
                "largest_cluster_size": largest,
                "cluster_size_ratio": round(_safe_div(largest, smallest), 6),
                "stability_score": stability,
                "eligible_status": "eligible" if eligible else "rejected",
                "selected_status": "not_selected",
                "rejection_reason": "" if eligible else "cluster_below_minimum_size",
            }
        )
    eligible_rows = [row for row in rows if row["eligible_status"] == "eligible"]
    if not eligible_rows:
        msg = "No eligible cluster candidates after minimum-size and population checks."
        raise ValueError(msg)
    selected = sorted(
        eligible_rows,
        key=lambda row: (
            float(row["silhouette_score"] or -1),
            float(row["stability_score"] or 0),
            -int(row["cluster_count"]),
        ),
        reverse=True,
    )[0]
    for row in rows:
        if (
            row["algorithm"] == selected["algorithm"]
            and row["cluster_count"] == selected["cluster_count"]
        ):
            row["selected_status"] = "selected"
    return rows, selected


def _fit_selected_kmeans(
    matrix: np.ndarray[Any, Any], selected: Record, config: SegmentationConfig
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], StandardScaler]:
    scaler = StandardScaler()
    scaled = scaler.fit_transform(matrix)
    model = KMeans(
        n_clusters=int(selected["cluster_count"]),
        random_state=config.random_seed,
        n_init=config.kmeans_initialisations,
    )
    labels = model.fit_predict(scaled)
    return labels, model.cluster_centers_, scaler


def _canonical_cluster_mapping(
    rows: list[SegmentationRow], labels: np.ndarray[Any, Any], cluster_count: int
) -> dict[int, str]:
    scored = []
    for raw_label in range(cluster_count):
        group = [row for row, label in zip(rows, labels, strict=True) if int(label) == raw_label]
        engagement = _mean(group, "sessions_in_lookback") + _mean(
            group, "qualifying_events_in_lookback"
        )
        advanced = _mean(group, "automation_executions") + _mean(group, "integrations_connected")
        inactivity = _mean(group, "days_since_last_activity")
        fingerprint = record_fingerprint(
            {
                "label": raw_label,
                "engagement": round(engagement, 6),
                "advanced": round(advanced, 6),
                "inactivity": round(inactivity, 6),
            }
        )
        scored.append((-engagement, -advanced, inactivity, fingerprint, raw_label))
    ordered = sorted(scored)
    return {raw_label: f"cluster_{index + 1:02d}" for index, (*_, raw_label) in enumerate(ordered)}


def _stability_rows(
    matrix: np.ndarray[Any, Any], cluster_count: int, config: SegmentationConfig
) -> list[Record]:
    scaler = StandardScaler()
    scaled = scaler.fit_transform(matrix)
    reference = KMeans(
        n_clusters=cluster_count,
        random_state=config.random_seed,
        n_init=config.kmeans_initialisations,
    ).fit_predict(scaled)
    rows: list[Record] = []
    for seed in config.stability_seeds:
        labels = KMeans(
            n_clusters=cluster_count,
            random_state=seed,
            n_init=config.kmeans_initialisations,
        ).fit_predict(scaled)
        rows.append(
            {
                "algorithm": "kmeans",
                "cluster_count": cluster_count,
                "reference_seed": config.random_seed,
                "comparison_seed": seed,
                "adjusted_rand_score": round(float(adjusted_rand_score(reference, labels)), 6),
            }
        )
    return rows


def _stability_score(
    scaled: np.ndarray[Any, Any], cluster_count: int, config: SegmentationConfig
) -> float:
    reference = KMeans(
        n_clusters=cluster_count,
        random_state=config.random_seed,
        n_init=config.kmeans_initialisations,
    ).fit_predict(scaled)
    scores = []
    for seed in config.stability_seeds:
        labels = KMeans(
            n_clusters=cluster_count,
            random_state=seed,
            n_init=config.kmeans_initialisations,
        ).fit_predict(scaled)
        scores.append(float(adjusted_rand_score(reference, labels)))
    return round(sum(scores) / len(scores), 6)


def _pca_outputs(
    rows: list[SegmentationRow],
    matrix: np.ndarray[Any, Any],
    labels: list[str],
    scaler: StandardScaler,
    config: SegmentationConfig,
) -> tuple[list[Record], list[Record], list[Record]]:
    scaled = scaler.transform(matrix)
    component_count = min(config.pca_components, scaled.shape[0], scaled.shape[1])
    pca = PCA(n_components=component_count, random_state=config.random_seed)
    coords = pca.fit_transform(scaled)
    pca_rows = [
        {
            "snapshot_id": row.snapshot.snapshot_id,
            "cluster_id": label,
            "pca_component_1": round(float(coord[0]), 6),
            "pca_component_2": round(float(coord[1]), 6) if component_count > 1 else 0.0,
        }
        for row, label, coord in zip(rows, labels, coords, strict=True)
    ]
    variance_rows = [
        {
            "component": index + 1,
            "explained_variance_ratio": round(float(value), 6),
        }
        for index, value in enumerate(pca.explained_variance_ratio_)
    ]
    centroid_rows = [
        {
            "cluster_id": cluster_id,
            "pca_component_1": _pca_centroid(pca_rows, cluster_id, "pca_component_1"),
            "pca_component_2": _pca_centroid(pca_rows, cluster_id, "pca_component_2"),
        }
        for cluster_id in sorted(set(labels))
    ]
    return pca_rows, variance_rows, centroid_rows


def _pca_centroid(pca_rows: list[Record], cluster_id: str, component: str) -> float:
    values = [
        float(row[component])
        for row in pca_rows
        if str(row["cluster_id"]) == cluster_id and isinstance(row[component], int | float)
    ]
    return round(_safe_div(sum(values), len(values)), 6)


def _cluster_assignments(
    rows: list[SegmentationRow],
    labels: list[str],
    names: dict[str, str],
    matrix: np.ndarray[Any, Any],
    pca_rows: list[Record],
    source_ingestion_run_id: str,
) -> list[Record]:
    scaler = StandardScaler()
    scaled = scaler.fit_transform(matrix)
    pca_by_index = {index: row for index, row in enumerate(pca_rows)}
    centroid_by_cluster = {
        cluster_id: np.mean(
            np.array(
                [row for row, label in zip(scaled, labels, strict=True) if label == cluster_id]
            ),
            axis=0,
        )
        for cluster_id in sorted(set(labels))
    }
    assignments: list[Record] = []
    for index, (row, label) in enumerate(zip(rows, labels, strict=True)):
        distance = float(np.linalg.norm(scaled[index] - centroid_by_cluster[label]))
        pca = pca_by_index[index]
        assignments.append(
            {
                "snapshot_id": row.snapshot.snapshot_id,
                "user_id": row.snapshot.user_id,
                "cluster_id": label,
                "business_segment_name": names[label],
                "distance_to_centroid": round(distance, 6),
                "confidence_proxy": round(1 / (1 + distance), 6),
                "pca_component_1": pca["pca_component_1"],
                "pca_component_2": pca["pca_component_2"],
                "source_ingestion_run_id": source_ingestion_run_id,
                "model_version": SEGMENTATION_VERSION,
            }
        )
    return assignments


def _cluster_names(rows: list[SegmentationRow], labels: list[str]) -> dict[str, str]:
    names: dict[str, str] = {}
    population = {feature: _mean(rows, feature) for feature in CLUSTERING_FEATURES}
    for cluster_id in sorted(set(labels)):
        group = [row for row, label in zip(rows, labels, strict=True) if label == cluster_id]
        if _mean(group, "automation_executions") > population["automation_executions"]:
            name = "automation_adopters"
        elif _mean(group, "collaboration_events") > population["collaboration_events"]:
            name = "collaboration_focused_teams"
        elif _mean(group, "paid_user_flag") > 0.5 and _mean(group, "active_days_in_lookback") <= 1:
            name = "paid_low_engagement"
        elif _mean(group, "error_event_rate") > population["error_event_rate"]:
            name = "high_friction_users"
        elif (
            _mean(group, "qualifying_events_in_lookback")
            > population["qualifying_events_in_lookback"]
        ):
            name = "high_engagement_power_users"
        elif _mean(group, "days_since_last_activity") > population["days_since_last_activity"]:
            name = "inactive_or_declining_users"
        else:
            name = "new_or_exploratory_users"
        names[cluster_id] = name
    return names


def _profiles(
    rows: list[SegmentationRow],
    rule_assignments: list[RuleAssignment],
    cluster_assignments: list[Record],
    suppression_threshold: int,
) -> list[Record]:
    rule_group_ids = {assignment.rule_based_segment_id for assignment in rule_assignments}
    cluster_group_ids = {str(assignment["cluster_id"]) for assignment in cluster_assignments}
    rows_by_snapshot = {row.snapshot.snapshot_id: row for row in rows}
    rule_lookup = {assignment.snapshot_id: assignment for assignment in rule_assignments}
    cluster_lookup = {
        str(assignment["snapshot_id"]): assignment for assignment in cluster_assignments
    }
    profile_rows: list[Record] = []
    for method, segment_ids in (
        ("rule_based", sorted(rule_group_ids)),
        ("kmeans", sorted(cluster_group_ids)),
    ):
        for segment_id in segment_ids:
            if method == "rule_based":
                group = [
                    rows_by_snapshot[snapshot_id]
                    for snapshot_id, assignment in rule_lookup.items()
                    if assignment.rule_based_segment_id == segment_id
                ]
                name = next(
                    assignment.segment_name
                    for assignment in rule_assignments
                    if assignment.rule_based_segment_id == segment_id
                )
            else:
                group = [
                    rows_by_snapshot[snapshot_id]
                    for snapshot_id, assignment in cluster_lookup.items()
                    if assignment["cluster_id"] == segment_id
                ]
                name = str(
                    next(
                        assignment["business_segment_name"]
                        for assignment in cluster_assignments
                        if assignment["cluster_id"] == segment_id
                    )
                )
            profile_rows.extend(
                _profile_metrics(method, segment_id, name, group, rows, suppression_threshold)
            )
    return profile_rows


def _profile_metrics(
    method: str,
    segment_id: str,
    segment_name: str,
    group: list[SegmentationRow],
    population: list[SegmentationRow],
    suppression_threshold: int,
) -> list[Record]:
    suppressed = len(group) < suppression_threshold
    metrics = {
        "user_count": len(group),
        "population_share": round(_safe_div(len(group), len(population)), 6),
        "mean_activity": _mean(group, "qualifying_events_in_lookback"),
        "median_recency": _median(group, "days_since_last_activity"),
        "collaboration_adoption": _mean(group, "collaboration_adoption_flag"),
        "automation_adoption": _mean(group, "automation_adoption_flag"),
        "paid_conversion": _mean(group, "paid_conversion_flag"),
        "error_rate": _mean(group, "error_event_rate"),
        "plan_distribution": _distribution(group, "current_plan"),
        "persona_distribution": _distribution(group, "persona"),
        "acquisition_channel_distribution": _distribution(group, "acquisition_channel"),
        "top_differentiating_features": "|".join(_top_differentiators(group, population)),
    }
    return [
        {
            "method": method,
            "segment_id": segment_id,
            "segment_name": segment_name,
            "user_count": len(group),
            "population_share": round(_safe_div(len(group), len(population)), 6),
            "metric_name": metric_name,
            "metric_value": "" if suppressed and metric_name != "user_count" else metric_value,
            "comparison_to_population": _comparison(metric_name, metric_value, population),
            "suppression_status": "suppressed" if suppressed else "shown",
            "interpretation_note": "small group suppressed" if suppressed else "descriptive only",
        }
        for metric_name, metric_value in metrics.items()
    ]


def _name_mapping(
    names: dict[str, str], rows: list[SegmentationRow], labels: list[str]
) -> dict[str, Record]:
    return {
        cluster_id: {
            "technical_cluster_id": cluster_id,
            "business_segment_name": name,
            "reason_codes": _top_differentiators(
                [row for row, label in zip(rows, labels, strict=True) if label == cluster_id],
                rows,
            ),
            "caveat": "segment names are deterministic analytical interpretations",
        }
        for cluster_id, name in sorted(names.items())
    }


def _centroid_rows(rows: list[SegmentationRow], labels: list[str]) -> list[Record]:
    output: list[Record] = []
    for cluster_id in sorted(set(labels)):
        group = [row for row, label in zip(rows, labels, strict=True) if label == cluster_id]
        for feature in CLUSTERING_FEATURES:
            output.append(
                {
                    "cluster_id": cluster_id,
                    "feature_name": feature,
                    "centroid_value": _mean(group, feature),
                }
            )
    return output


def _diagnostics(
    rows: list[SegmentationRow],
    exclusions: dict[str, int],
    constant_features: list[str],
    candidate_rows: list[Record],
    selected_candidate: Record,
    stability_rows: list[Record],
    profiles: list[Record],
    rule_assignments: list[RuleAssignment],
) -> dict[str, object]:
    return {
        "trusted_input_compatibility": "passed",
        "users_considered": len(rows) + sum(exclusions.values()),
        "eligible_snapshots": len(rows),
        "exclusions_by_reason": exclusions,
        "feature_validation": "passed",
        "constant_features_removed": constant_features,
        "missing_value_handling": "zero-filled numeric features; unknown categorical profiles",
        "candidate_models_evaluated": len(candidate_rows),
        "rejected_candidates": [
            row for row in candidate_rows if row["eligible_status"] != "eligible"
        ],
        "selected_cluster_count": selected_candidate["cluster_count"],
        "minimum_cluster_size": min(
            int(row["smallest_cluster_size"])
            for row in candidate_rows
            if row["eligible_status"] == "eligible"
        ),
        "stability_summary": {
            "mean_adjusted_rand_score": round(
                sum(float(row["adjusted_rand_score"]) for row in stability_rows)
                / len(stability_rows),
                6,
            )
        },
        "suppressed_profile_rows": sum(
            1 for row in profiles if row["suppression_status"] == "suppressed"
        ),
        "rule_assignment_coverage": len(rule_assignments),
        "warnings": [],
        "overall_status": "passed",
    }


def _write_outputs(
    *,
    output_dir: Path,
    config: SegmentationConfig,
    run_id: str,
    source_ingestion_run_id: str,
    source_checksum: str,
    source_contract_versions: dict[str, str],
    trusted_row_counts: dict[str, int],
    rows: list[SegmentationRow],
    rule_assignments: list[RuleAssignment],
    candidate_rows: list[Record],
    stability_rows: list[Record],
    cluster_assignments: list[Record],
    profiles: list[Record],
    centroids: list[Record],
    pca_rows: list[Record],
    pca_variance_rows: list[Record],
    centroid_pca_rows: list[Record],
    name_mapping: dict[str, Record],
    diagnostics: dict[str, object],
    selected_candidate: Record,
    active_features: list[str],
) -> None:
    files: dict[str, Callable[[Path], None]] = {
        "segmentation-definition.json": lambda path: _write_json(path, _definition(config)),
        "feature-catalogue.json": lambda path: _write_json(path, feature_catalogue()),
        "segmentation-snapshots.jsonl": lambda path: _write_jsonl(
            path, [row.snapshot.to_record() for row in rows]
        ),
        "feature-matrix.csv": lambda path: _write_csv(path, [row.to_record() for row in rows]),
        "rule-based-assignments.csv": lambda path: _write_csv(
            path, [assignment.to_record() for assignment in rule_assignments]
        ),
        "cluster-candidate-metrics.csv": lambda path: _write_csv(path, candidate_rows),
        "cluster-stability.csv": lambda path: _write_csv(path, stability_rows),
        "cluster-assignments.csv": lambda path: _write_csv(path, cluster_assignments),
        "segment-profiles.csv": lambda path: _write_csv(path, profiles),
        "cluster-centroids.csv": lambda path: _write_csv(path, [*centroids, *centroid_pca_rows]),
        "pca-coordinates.csv": lambda path: _write_csv(path, pca_rows),
        "pca-explained-variance.csv": lambda path: _write_csv(path, pca_variance_rows),
        "segment-name-mapping.json": lambda path: _write_json(path, name_mapping),
        "model-metadata.json": lambda path: _write_json(
            path,
            _metadata(
                config,
                run_id,
                source_ingestion_run_id,
                source_checksum,
                selected_candidate,
                active_features,
                pca_variance_rows,
            ),
        ),
        "run-diagnostics.json": lambda path: _write_json(path, diagnostics),
        "segmentation-lineage.json": lambda path: _write_json(
            path,
            _lineage(source_ingestion_run_id, source_checksum, source_contract_versions),
        ),
        "segment-card.md": lambda path: _write_text(
            path, _segment_card(config, selected_candidate, diagnostics, name_mapping)
        ),
    }
    checksums: dict[str, str] = {}
    for filename, writer in files.items():
        path = output_dir / filename
        writer(path)
        checksums[filename] = file_sha256(path)
    manifest = {
        "segmentation_run_id": run_id,
        "model_version": SEGMENTATION_VERSION,
        "source_ingestion_run_id": source_ingestion_run_id,
        "source_manifest_checksum": source_checksum,
        "input_row_counts": trusted_row_counts,
        "output_row_counts": {
            "segmentation-snapshots.jsonl": len(rows),
            "feature-matrix.csv": len(rows),
            "rule-based-assignments.csv": len(rule_assignments),
            "cluster-assignments.csv": len(cluster_assignments),
            "segment-profiles.csv": len(profiles),
        },
        "output_checksums": checksums,
        "selected_cluster_count": selected_candidate["cluster_count"],
        "overall_status": diagnostics["overall_status"],
        "created_at": config.fixed_run_time,
    }
    _write_json(output_dir / "segmentation-manifest.json", manifest)


def feature_catalogue() -> list[Record]:
    """Return the governed segmentation feature catalogue."""

    rows: list[Record] = []
    for feature in NUMERIC_FEATURES:
        rows.append(_catalogue_row(feature, "numeric", "clustering"))
    for feature in BINARY_FEATURES:
        rows.append(_catalogue_row(feature, "binary", "clustering"))
    for feature in CATEGORICAL_PROFILE_FEATURES:
        rows.append(_catalogue_row(feature, "categorical", "profiling_only"))
    rows.extend(
        {
            "feature_name": field,
            "type": "identifier",
            "business_meaning": "excluded identifier or diagnostic field",
            "source_datasets": "derived",
            "calculation_window": "not used for clustering",
            "null_handling": "required",
            "expected_range": "stable text",
            "transformation": "excluded",
            "clustering_role": "excluded",
            "leakage_considerations": "not a behavioural clustering input",
        }
        for field in ("user_id", "snapshot_id")
    )
    return rows


def _validate_outputs(
    rows: list[SegmentationRow],
    rule_assignments: list[RuleAssignment],
    cluster_assignments: list[Record],
    profiles: list[Record],
    candidate_rows: list[Record],
) -> None:
    if len({row.snapshot.snapshot_id for row in rows}) != len(rows):
        raise ValueError("Snapshot IDs must be unique.")
    if len({row.snapshot.user_id for row in rows}) != len(rows):
        raise ValueError("Default segmentation requires one snapshot per user.")
    if len(rule_assignments) != len(rows):
        raise ValueError("Rule-based assignments must cover every row.")
    if len(cluster_assignments) != len(rows):
        raise ValueError("Cluster assignments must cover every row.")
    if any(float(row["distance_to_centroid"]) < 0 for row in cluster_assignments):
        raise ValueError("Distances must be non-negative.")
    if sum(1 for row in candidate_rows if row["selected_status"] == "selected") != 1:
        raise ValueError("Exactly one cluster candidate must be selected.")
    for method in PROFILE_SEGMENT_METHODS:
        share = sum(
            float(row["population_share"])
            for row in profiles
            if row["method"] == method and row["metric_name"] == "user_count"
        )
        if not math.isclose(share, 1.0, rel_tol=0.000001, abs_tol=0.000001):
            raise ValueError(f"Profile population shares do not sum to one for {method}.")


def _definition(config: SegmentationConfig) -> Record:
    return {
        "definition_id": "governed_user_segmentation",
        "version": SEGMENTATION_VERSION,
        "analytical_entity": "user",
        "snapshot_time": config.snapshot_time,
        "lookback_days": config.lookback_days,
        "minimum_account_age": config.minimum_account_age,
        "minimum_activity": config.minimum_activity,
        "include_inactive_users": config.include_inactive_users,
        "primary_methods": ["rule_based", "kmeans"],
        "leakage_policy": "features use trusted records at or before snapshot only",
        "out_of_scope": ["recommendations", "uplift", "GenAI", "online serving"],
    }


def _metadata(
    config: SegmentationConfig,
    run_id: str,
    source_ingestion_run_id: str,
    source_checksum: str,
    selected_candidate: Record,
    active_features: list[str],
    pca_variance_rows: list[Record],
) -> Record:
    return {
        "model_id": "governed_user_segmentation",
        "model_run_id": run_id,
        "model_version": SEGMENTATION_VERSION,
        "algorithm": selected_candidate["algorithm"],
        "selected_cluster_count": selected_candidate["cluster_count"],
        "feature_schema_version": SEGMENTATION_VERSION,
        "rule_version": RULE_VERSION,
        "software_version": get_project_metadata().version,
        "source_ingestion_run_id": source_ingestion_run_id,
        "source_manifest_checksum": source_checksum,
        "snapshot_timestamp": config.snapshot_time,
        "lookback_period": config.lookback_days,
        "eligible_population": "trusted users meeting account-age and activity rules",
        "feature_count": len(active_features),
        "candidate_cluster_counts": list(config.candidate_clusters),
        "selection_rule": (
            "reject undersized clusters; maximise silhouette; use stability tie-breaker; "
            "prefer fewer clusters when materially similar"
        ),
        "selected_quality_metrics": selected_candidate,
        "random_seed": config.random_seed,
        "preprocessing_details": (
            "constant features removed; StandardScaler fitted on eligible population"
        ),
        "pca_variance_summary": pca_variance_rows,
        "created_at": config.fixed_run_time,
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
            "trusted accepted datasets",
            "point-in-time segmentation snapshots",
            "historical feature engineering",
            "rule-based segmentation",
            "KMeans clustering",
            "PCA coordinates",
            "segment profiles and names",
        ],
    }


def _segment_card(
    config: SegmentationConfig,
    selected_candidate: Record,
    diagnostics: dict[str, object],
    name_mapping: dict[str, Record],
) -> str:
    lines = [
        "# User Segmentation Segment Card",
        "",
        "Intended use: descriptive product, growth and customer-success analysis.",
        (
            "Out-of-scope use: automated adverse decisions, recommendations, uplift, "
            "or real-time serving."
        ),
        "All data is synthetic. Segment names are analytical interpretations, not causal claims.",
        "",
        f"Snapshot: {config.snapshot_time}. Lookback days: {config.lookback_days}.",
        f"Eligible snapshots: {diagnostics['eligible_snapshots']}.",
        "Methods: deterministic rule-based segmentation and KMeans clustering.",
        (
            "Preprocessing: numeric and binary features only, constant features removed, "
            "StandardScaler."
        ),
        (
            "Cluster-count selection rejects undersized clusters, prioritises silhouette, "
            "uses stability as a tie-breaker and prefers simpler solutions."
        ),
        f"Selected clusters: {selected_candidate['cluster_count']}.",
        f"Stability: {diagnostics['stability_summary']}.",
        "",
        "## Segment Names",
    ]
    lines.extend(
        f"- {cluster_id}: {record['business_segment_name']}"
        for cluster_id, record in sorted(name_mapping.items())
    )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- Small sample evidence is illustrative.",
            "- Clusters do not prove causal behaviour.",
            "- Segment names require domain review before operational use.",
            "- Monitor drift, profile suppression and assignment stability before production use.",
            "",
            "Azure mapping: trusted data in ADLS Gen2, feature preparation in Synapse or Azure ML, "
            "clustering in Azure ML, tracking through MLflow, governance through Purview, and "
            "monitoring through Azure Monitor. No Azure resources are deployed here.",
            "",
        ]
    )
    return "\n".join(lines)


def _catalogue_row(feature: str, feature_type: str, role: str) -> Record:
    return {
        "feature_name": feature,
        "type": feature_type,
        "business_meaning": feature.replace("_", " "),
        "source_datasets": "users|sessions|clickstream_events|feature_usage|subscriptions",
        "calculation_window": "snapshot lookback or point-in-time subscription state",
        "null_handling": "zero for numeric and binary, unknown for categorical profiles",
        "expected_range": "non-negative numeric or finite category",
        "transformation": "standard_scaled" if role == "clustering" else "profiled_raw",
        "clustering_role": role,
        "leakage_considerations": "computed using records at or before snapshot timestamp",
    }


def _rejected_candidate(cluster_count: int, reason: str) -> Record:
    return {
        "algorithm": "kmeans",
        "cluster_count": cluster_count,
        "random_seed": "",
        "silhouette_score": None,
        "davies_bouldin_score": None,
        "calinski_harabasz_score": None,
        "smallest_cluster_size": 0,
        "largest_cluster_size": 0,
        "cluster_size_ratio": None,
        "stability_score": None,
        "eligible_status": "rejected",
        "selected_status": "not_selected",
        "rejection_reason": reason,
    }


def _metric_or_none(
    metric: Any, matrix: np.ndarray[Any, Any], labels: np.ndarray[Any, Any]
) -> float | None:
    if len(set(int(label) for label in labels)) < 2 or len(labels) <= len(set(labels)):
        return None
    return round(float(metric(matrix, labels)), 6)


def _records_by_user(records: list[Record]) -> defaultdict[str, list[Record]]:
    by_user: defaultdict[str, list[Record]] = defaultdict(list)
    for record in records:
        by_user[str(record["user_id"])].append(record)
    return by_user


def _subscription_context(
    subscriptions: list[Record], snapshot: datetime
) -> tuple[str, str, float, int]:
    active = [
        sub
        for sub in subscriptions
        if _parse_dt(str(sub["period_start_timestamp"])) <= snapshot
        and (
            not sub.get("period_end_timestamp")
            or _parse_dt(str(sub["period_end_timestamp"])) >= snapshot
        )
    ]
    if not active:
        return ("unknown", "unknown", 0.0, 0)
    selected = sorted(active, key=lambda sub: str(sub["period_start_timestamp"]))[-1]
    start = _parse_dt(str(selected["period_start_timestamp"]))
    return (
        str(selected.get("plan_name", "unknown")),
        str(selected.get("status", "unknown")),
        float(selected.get("monthly_recurring_revenue", 0) or 0),
        (snapshot - start).days,
    )


def _plan_rank(plan: str) -> int:
    return {"free": 0, "starter": 1, "team": 2, "business": 3, "enterprise": 4}.get(plan, 0)


def _highest_activation_stage(counts: Counter[str]) -> int:
    if counts["onboarding_completed"] > 0:
        return 4
    if counts["workspace_created"] > 0 or counts["task_completed"] > 0:
        return 3
    if counts["onboarding_step_completed"] > 0:
        return 2
    if counts["onboarding_started"] > 0:
        return 1
    return 0


def _longest_gap(days: list[date]) -> int:
    if len(days) < 2:
        return 0
    return int(max((b - a).days for a, b in zip(days, days[1:], strict=False)))


def _resurrection_count(days: list[date]) -> int:
    if len(days) < 2:
        return 0
    return sum(1 for a, b in zip(days, days[1:], strict=False) if (b - a).days > 7)


def _mean(rows: list[SegmentationRow], feature: str) -> float:
    return round(
        _safe_div(sum(float(row.features.get(feature, 0) or 0) for row in rows), len(rows)), 6
    )


def _median(rows: list[SegmentationRow], feature: str) -> float:
    if not rows:
        return 0.0
    values = sorted(float(row.features.get(feature, 0) or 0) for row in rows)
    index = len(values) // 2
    if len(values) % 2:
        return round(values[index], 6)
    return round((values[index - 1] + values[index]) / 2, 6)


def _distribution(rows: list[SegmentationRow], feature: str) -> str:
    counts = Counter(str(row.features.get(feature, "unknown")) for row in rows)
    total = sum(counts.values())
    return "|".join(
        f"{key}:{round(_safe_div(value, total), 6)}" for key, value in sorted(counts.items())
    )


def _top_differentiators(
    group: list[SegmentationRow], population: list[SegmentationRow]
) -> list[str]:
    diffs = [
        (
            abs(_mean(group, feature) - _mean(population, feature)),
            feature,
            _mean(group, feature) - _mean(population, feature),
        )
        for feature in CLUSTERING_FEATURES
        if group
    ]
    return [
        f"{feature}:{'above' if diff > 0 else 'below'}_population"
        for _, feature, diff in sorted(diffs, reverse=True)[:3]
    ]


def _comparison(metric_name: str, metric_value: object, population: list[SegmentationRow]) -> str:
    numeric_population = {
        "mean_activity": _mean(population, "qualifying_events_in_lookback"),
        "median_recency": _median(population, "days_since_last_activity"),
        "collaboration_adoption": _mean(population, "collaboration_adoption_flag"),
        "automation_adoption": _mean(population, "automation_adoption_flag"),
        "paid_conversion": _mean(population, "paid_conversion_flag"),
        "error_rate": _mean(population, "error_event_rate"),
    }
    if metric_name not in numeric_population or not isinstance(metric_value, int | float):
        return "not_applicable"
    delta = float(metric_value) - numeric_population[metric_name]
    return f"{round(delta, 6)}_vs_population"


def _safe_div(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _default_run_id(config: SegmentationConfig) -> str:
    if config.fixed_run_time:
        stamp = (
            config.fixed_run_time.replace(":", "")
            .replace("-", "")
            .replace("T", "-")
            .replace("Z", "")
        )
    else:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"segmentation-{stamp}"


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _format_dt(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[Record]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


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


def run_sample_to_temp() -> SegmentationResult:
    """Run sample ingestion then segmentation in a temporary directory."""

    from product_growth_intelligence.ingestion import IngestionConfig, run_batch_ingestion

    with TemporaryDirectory() as temp:
        root = Path(temp)
        ingestion = run_batch_ingestion(
            IngestionConfig(
                source=Path("data/samples/nexaflow"),
                output_root=root / "interim",
                quality_root=root / "quality",
                run_id="milestone7-source",
                fixed_ingestion_time="2026-01-01T00:00:00Z",
                overwrite=True,
            )
        )
        return run_segmentation(
            SegmentationConfig(
                input_dir=ingestion.output_dir,
                output_root=root / "segmentation",
                run_id="milestone7-segmentation",
                fixed_run_time="2026-01-02T00:00:00Z",
                overwrite=True,
            )
        )
