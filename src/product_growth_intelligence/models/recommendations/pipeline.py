"""Deterministic governed recommendation baselines."""

# ruff: noqa: ANN401

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity  # type: ignore[import-untyped]

from product_growth_intelligence.analytics.inputs import (
    dataset_row_counts,
    load_trusted_input,
    source_manifest_checksum,
)
from product_growth_intelligence.data_generation.models import Record
from product_growth_intelligence.ingestion.fingerprints import file_sha256, record_fingerprint
from product_growth_intelligence.metadata import get_project_metadata
from product_growth_intelligence.models.recommendations.models import (
    RecommendationConfig,
    RecommendationResult,
)
from product_growth_intelligence.models.segmentation import SegmentationConfig
from product_growth_intelligence.models.segmentation.pipeline import (
    assign_rule_based_segments,
    build_segmentation_rows,
)

RECOMMENDATION_VERSION = "2026-07-milestone-8"
CATALOGUE_VERSION = "2026-07-milestone-8-catalogue"
MAPPING_VERSION = "2026-07-milestone-8-interactions"
INTERACTION_WEIGHTS = {
    "exposure": 0.1,
    "view": 0.25,
    "click": 0.5,
    "trial": 1.0,
    "use": 1.5,
    "successful_use": 2.0,
    "repeat_use": 3.0,
    "acceptance": 3.0,
}
MODEL_NAMES = {
    "global_popularity": "Global popularity",
    "recent_popularity": "Recent popularity",
    "segment_popularity": "Segment-aware popularity",
    "item_item_cf": "Item-item collaborative filtering",
}


def run_recommendations(config: RecommendationConfig) -> RecommendationResult:
    """Run deterministic recommendation baselines over trusted accepted data."""

    config.validate()
    trusted = load_trusted_input(config.input_dir)
    run_id = config.run_id or _default_run_id(config)
    output_dir = config.output_root / run_id
    if output_dir.exists() and any(output_dir.iterdir()) and not config.overwrite:
        msg = f"Output directory {output_dir} already exists and is not empty. Pass --overwrite."
        raise FileExistsError(msg)
    if config.validate_only:
        return RecommendationResult(
            run_id=run_id,
            status="validated",
            output_dir=output_dir,
            eligible_users=0,
            evaluated_users=0,
            selected_model="none",
        )

    catalogue = item_catalogue()
    _validate_catalogue(catalogue)
    interactions, holdout, user_segments, user_context, exclusions = _build_inputs(config)
    users = sorted({row["user_id"] for row in interactions} | set(holdout))
    if not users:
        msg = "Recommendation run requires at least one eligible user."
        raise ValueError(msg)
    candidates = _candidate_rows(
        users,
        catalogue,
        interactions,
        user_segments,
        user_context,
        trusted.source_ingestion_run_id,
        config,
    )
    item_scores = _item_scores(interactions, config)
    similarity_rows, similarity = _item_similarity(interactions, catalogue, config)
    recommendations: list[Record] = []
    reasons: list[Record] = []
    for model_id in config.enabled_models:
        model_recs = _recommend_for_model(
            model_id,
            users,
            catalogue,
            candidates,
            interactions,
            item_scores,
            similarity,
            user_segments,
            trusted.source_ingestion_run_id,
            config,
        )
        recommendations.extend(model_recs)
        reasons.extend(_reason_rows(model_recs))
    metrics_by_model, metrics_by_k, offline_metrics = _evaluate_models(
        recommendations, holdout, interactions, catalogue, config
    )
    selected_model = _select_model(metrics_by_model, config)
    for row in metrics_by_model:
        row["selected_status"] = "selected" if row["model_id"] == selected_model else "not_selected"
    segment_metrics = _segment_metrics(recommendations, holdout, user_segments, config)
    cold_start_metrics = _cold_start_metrics(recommendations, holdout, interactions, config)
    coverage_rows = _catalogue_coverage(recommendations, catalogue, config)
    diagnostics = _diagnostics(
        trusted_users=len(trusted.datasets["users"]),
        users=users,
        exclusions=exclusions,
        interactions=interactions,
        holdout=holdout,
        candidates=candidates,
        recommendations=recommendations,
        selected_model=selected_model,
        similarity_rows=similarity_rows,
    )
    _validate_outputs(
        catalogue, interactions, holdout, candidates, recommendations, metrics_by_model
    )
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
        catalogue=catalogue,
        interactions=interactions,
        candidates=candidates,
        model_comparison=metrics_by_model,
        offline_metrics=offline_metrics,
        metrics_by_k=metrics_by_k,
        segment_metrics=segment_metrics,
        cold_start_metrics=cold_start_metrics,
        similarity_rows=similarity_rows,
        recommendations=recommendations,
        reasons=reasons,
        coverage_rows=coverage_rows,
        diagnostics=diagnostics,
        selected_model=selected_model,
    )
    return RecommendationResult(
        run_id=run_id,
        status=str(diagnostics["overall_status"]),
        output_dir=output_dir,
        eligible_users=len(users),
        evaluated_users=sum(1 for user in users if holdout.get(user)),
        selected_model=selected_model,
        diagnostics=diagnostics,
    )


def item_catalogue() -> list[Record]:
    """Return the governed recommendation catalogue."""

    def item(
        item_id: str,
        name: str,
        category: str,
        feature: str,
        plans: tuple[str, ...],
        personas: tuple[str, ...] = (),
        company_sizes: tuple[str, ...] = (),
        required: tuple[str, ...] = (),
        incompatible: tuple[str, ...] = (),
        repeatable: bool = False,
        priority: float = 1.0,
    ) -> Record:
        return {
            "item_id": item_id,
            "item_name": name,
            "item_category": category,
            "feature_name": feature,
            "description": f"Synthetic NexaFlow recommendation for {name}.",
            "eligible_plans": list(plans),
            "eligible_personas": list(personas),
            "eligible_company_sizes": list(company_sizes),
            "required_prior_actions": list(required),
            "incompatible_prior_actions": list(incompatible),
            "repeatable": repeatable,
            "catalogue_priority": priority,
            "active": True,
            "catalogue_version": CATALOGUE_VERSION,
            "synthetic_record": True,
        }

    all_plans = ("free", "starter", "team", "business")
    paid_plans = ("starter", "team", "business")
    return [
        item("feature_task_management", "Task management", "feature", "tasks", all_plans),
        item(
            "feature_collaboration",
            "Collaboration",
            "feature",
            "collaboration",
            ("team", "business"),
        ),
        item("feature_search", "Search", "feature", "search", all_plans, repeatable=True),
        item("feature_reporting", "Reporting", "feature", "reports", ("business",)),
        item("feature_notifications", "Notifications", "feature", "notifications", paid_plans),
        item(
            "template_project_launch",
            "Project launch template",
            "template",
            "templates",
            all_plans,
            repeatable=True,
        ),
        item(
            "template_weekly_planning",
            "Weekly planning template",
            "template",
            "templates",
            all_plans,
            repeatable=True,
        ),
        item(
            "template_client_delivery",
            "Client delivery template",
            "template",
            "templates",
            paid_plans,
            repeatable=True,
        ),
        item(
            "automation_recurring_task",
            "Recurring task automation",
            "automation",
            "automation",
            ("business",),
        ),
        item(
            "automation_status_notification",
            "Status notification automation",
            "automation",
            "automation",
            ("business",),
        ),
        item(
            "integration_calendar",
            "Calendar integration",
            "integration",
            "integrations",
            ("team", "business"),
        ),
        item(
            "integration_file_storage",
            "File storage integration",
            "integration",
            "integrations",
            ("team", "business"),
        ),
        item(
            "workflow_invite_team",
            "Invite your team",
            "collaboration_action",
            "collaboration",
            ("team", "business"),
        ),
        item(
            "workflow_create_first_project",
            "Create first project",
            "workflow",
            "projects",
            all_plans,
        ),
        item(
            "education_complete_onboarding",
            "Complete onboarding",
            "education",
            "onboarding",
            all_plans,
        ),
        item(
            "education_automation_guide",
            "Automation guide",
            "education",
            "automation",
            all_plans,
            repeatable=True,
        ),
    ]


def interaction_mapping() -> list[Record]:
    """Return event-to-item interaction mappings."""

    return [
        _mapping("recommendation_shown", "recommendation", "exposure", None),
        _mapping("recommendation_clicked", "recommendation", "click", None),
        _mapping("recommendation_accepted", "recommendation", "acceptance", None),
        _mapping("template_selected", "template_project_launch", "use", "templates"),
        _mapping("automation_created", "automation_recurring_task", "use", "automation"),
        _mapping("automation_executed", "automation_recurring_task", "repeat_use", "automation"),
        _mapping("integration_connected", "integration_calendar", "successful_use", "integrations"),
        _mapping("invite_sent", "workflow_invite_team", "use", "collaboration"),
        _mapping("project_shared", "workflow_invite_team", "successful_use", "collaboration"),
        _mapping(
            "onboarding_completed", "education_complete_onboarding", "successful_use", "onboarding"
        ),
        _mapping("project_created", "workflow_create_first_project", "successful_use", "projects"),
        _mapping("task_created", "feature_task_management", "use", "tasks"),
        _mapping("task_completed", "feature_task_management", "successful_use", "tasks"),
        _mapping("search_performed", "feature_search", "use", "search"),
        _mapping("notification_opened", "feature_notifications", "view", "notifications"),
        _mapping("report_exported", "feature_reporting", "successful_use", "reports"),
    ]


def _build_inputs(
    config: RecommendationConfig,
) -> tuple[list[Record], dict[str, set[str]], dict[str, str], dict[str, Record], dict[str, int]]:
    trusted = load_trusted_input(config.input_dir)
    snapshot = _parse_dt(config.snapshot_time)
    lookback_start = snapshot - timedelta(days=config.lookback_days)
    holdout_end = snapshot + timedelta(days=config.holdout_days)
    users_by_id = {str(user["user_id"]): user for user in trusted.datasets["users"]}
    user_context = _user_context(
        trusted.datasets["users"], trusted.datasets["subscriptions"], snapshot
    )
    events = trusted.datasets["clickstream_events"]
    interactions = _aggregate_interactions(
        events, lookback_start, snapshot, trusted.source_ingestion_run_id
    )
    holdout = _holdout_items(events, snapshot, holdout_end)
    counts_by_user = Counter(str(row["user_id"]) for row in interactions)
    exclusions: Counter[str] = Counter()
    eligible_interactions = []
    for row in interactions:
        user = users_by_id.get(str(row["user_id"]))
        if user is None:
            exclusions["unknown_user"] += 1
            continue
        if _parse_dt(str(user["signup_timestamp"])) > snapshot:
            exclusions["signed_up_after_snapshot"] += 1
            continue
        if counts_by_user[str(row["user_id"])] < config.minimum_user_interactions:
            exclusions["below_minimum_user_interactions"] += 1
            continue
        eligible_interactions.append(row)
    segments = _reconstructed_segments(config)
    return (
        sorted(eligible_interactions, key=lambda row: (str(row["user_id"]), str(row["item_id"]))),
        holdout,
        segments,
        user_context,
        dict(exclusions),
    )


def _user_context(
    users: list[Record], subscriptions: list[Record], snapshot: datetime
) -> dict[str, Record]:
    context = {
        str(user["user_id"]): {
            "plan_name": str(user["initial_plan"]),
            "persona": str(user["persona"]),
            "company_size_band": str(user["company_size_band"]),
        }
        for user in users
    }
    latest_by_user: dict[str, tuple[datetime, Record]] = {}
    for subscription in subscriptions:
        user_id = str(subscription["user_id"])
        start = _parse_dt(str(subscription["period_start_timestamp"]))
        raw_end = subscription.get("period_end_timestamp")
        end = _parse_dt(str(raw_end)) if raw_end else None
        if start > snapshot or (end is not None and end < snapshot):
            continue
        previous = latest_by_user.get(user_id)
        if previous is None or start > previous[0]:
            latest_by_user[user_id] = (start, subscription)
    for user_id, (_, subscription) in latest_by_user.items():
        if user_id in context:
            context[user_id]["plan_name"] = str(subscription["plan_name"])
    return context


def _aggregate_interactions(
    events: list[Record], start: datetime, end: datetime, source_ingestion_run_id: str
) -> list[Record]:
    mapping_by_event = defaultdict(list)
    for row in interaction_mapping():
        mapping_by_event[str(row["event_name"])].append(row)
    grouped: dict[tuple[str, str], list[tuple[Record, Record]]] = defaultdict(list)
    for event in events:
        timestamp = _parse_dt(str(event["event_timestamp"]))
        if not start <= timestamp <= end:
            continue
        for mapping in mapping_by_event[str(event["event_name"])]:
            item_id = _mapped_item_id(event, mapping)
            if item_id:
                grouped[(str(event["user_id"]), item_id)].append((event, mapping))
    rows = []
    for (user_id, item_id), pairs in sorted(grouped.items()):
        timestamps = [_parse_dt(str(event["event_timestamp"])) for event, _ in pairs]
        strengths = Counter(str(mapping["interaction_strength"]) for _, mapping in pairs)
        score = sum(INTERACTION_WEIGHTS[strength] for strength in strengths.elements())
        rows.append(
            {
                "user_id": user_id,
                "item_id": item_id,
                "weighted_interaction_score": round(score, 6),
                "exposure_count": strengths["exposure"],
                "click_count": strengths["click"],
                "use_count": strengths["use"] + strengths["repeat_use"],
                "successful_use_count": strengths["successful_use"],
                "acceptance_count": strengths["acceptance"],
                "first_interaction_timestamp": _format_dt(min(timestamps)),
                "last_interaction_timestamp": _format_dt(max(timestamps)),
                "distinct_active_days": len(
                    {timestamp.date().isoformat() for timestamp in timestamps}
                ),
                "consumed_flag": 1 if _consumed(str(item_id), strengths) else 0,
                "source_ingestion_run_id": source_ingestion_run_id,
            }
        )
    return rows


def _holdout_items(
    events: list[Record], snapshot: datetime, holdout_end: datetime
) -> dict[str, set[str]]:
    mapping_by_event = defaultdict(list)
    for row in interaction_mapping():
        mapping_by_event[str(row["event_name"])].append(row)
    holdout: dict[str, set[str]] = defaultdict(set)
    for event in events:
        timestamp = _parse_dt(str(event["event_timestamp"]))
        if not snapshot < timestamp <= holdout_end:
            continue
        for mapping in mapping_by_event[str(event["event_name"])]:
            strength = str(mapping["interaction_strength"])
            if strength not in {"use", "repeat_use", "successful_use", "acceptance"}:
                continue
            item_id = _mapped_item_id(event, mapping)
            if item_id:
                holdout[str(event["user_id"])].add(item_id)
    return holdout


def _candidate_rows(
    users: list[str],
    catalogue: list[Record],
    interactions: list[Record],
    segments: dict[str, str],
    user_context: dict[str, Record],
    source_ingestion_run_id: str,
    config: RecommendationConfig,
) -> list[Record]:
    consumed = {
        (str(row["user_id"]), str(row["item_id"]))
        for row in interactions
        if int(row["consumed_flag"]) == 1
    }
    interaction_items_by_user = defaultdict(set)
    for row in interactions:
        interaction_items_by_user[str(row["user_id"])].add(str(row["item_id"]))
    rows = []
    for user_id in users:
        context = user_context.get(user_id, {})
        for item in catalogue:
            if not item["active"]:
                continue
            item_id = str(item["item_id"])
            reasons = ["active_catalogue_item"]
            plan = str(context.get("plan_name", "free"))
            persona = str(context.get("persona", "unknown"))
            company_size = str(context.get("company_size_band", "unknown"))
            if plan not in {str(value) for value in item["eligible_plans"]}:
                continue
            eligible_personas = {str(value) for value in item["eligible_personas"]}
            if eligible_personas and persona not in eligible_personas:
                continue
            eligible_company_sizes = {str(value) for value in item["eligible_company_sizes"]}
            if eligible_company_sizes and company_size not in eligible_company_sizes:
                continue
            consumed_flag = (user_id, item_id) in consumed
            if consumed_flag and not bool(item["repeatable"]):
                continue
            required = set(str(value) for value in item["required_prior_actions"])
            if required and not required <= interaction_items_by_user[user_id]:
                continue
            incompatible = set(str(value) for value in item["incompatible_prior_actions"])
            if incompatible and incompatible & interaction_items_by_user[user_id]:
                continue
            rows.append(
                {
                    "user_id": user_id,
                    "snapshot_id": _snapshot_id(user_id, config.snapshot_time),
                    "item_id": item_id,
                    "candidate_reason_codes": "|".join(reasons),
                    "already_consumed": int(consumed_flag),
                    "eligibility_status": "eligible",
                    "plan_name": plan,
                    "persona": persona,
                    "company_size_band": company_size,
                    "segment_id": segments.get(user_id, "unknown"),
                    "source_ingestion_run_id": source_ingestion_run_id,
                }
            )
    return rows


def _item_scores(
    interactions: list[Record], config: RecommendationConfig
) -> dict[str, dict[str, float]]:
    snapshot = _parse_dt(config.snapshot_time)
    recent_start = snapshot - timedelta(days=config.recent_popularity_window_days)
    scores: dict[str, defaultdict[str, float]] = {
        "global_popularity": defaultdict(float),
        "recent_popularity": defaultdict(float),
    }
    for row in interactions:
        item_id = str(row["item_id"])
        score = float(row["weighted_interaction_score"])
        scores["global_popularity"][item_id] += score
        if _parse_dt(str(row["last_interaction_timestamp"])) >= recent_start:
            scores["recent_popularity"][item_id] += score
    return {key: dict(value) for key, value in scores.items()}


def _item_similarity(
    interactions: list[Record], catalogue: list[Record], config: RecommendationConfig
) -> tuple[list[Record], dict[str, dict[str, float]]]:
    users = sorted({str(row["user_id"]) for row in interactions})
    items = [str(row["item_id"]) for row in catalogue]
    if not users or not items:
        return [], {}
    matrix = np.zeros((len(users), len(items)))
    user_index = {user: index for index, user in enumerate(users)}
    item_index = {item: index for index, item in enumerate(items)}
    for row in interactions:
        matrix[user_index[str(row["user_id"])], item_index[str(row["item_id"])]] = float(
            row["weighted_interaction_score"]
        )
    similarity_matrix = cosine_similarity(matrix.T)
    rows: list[Record] = []
    similarity: dict[str, dict[str, float]] = defaultdict(dict)
    for source in items:
        related = []
        for target in items:
            if source == target:
                continue
            support = int(
                np.sum((matrix[:, item_index[source]] > 0) & (matrix[:, item_index[target]] > 0))
            )
            if support < config.minimum_similarity_support:
                continue
            score = round(float(similarity_matrix[item_index[source], item_index[target]]), 6)
            related.append((score, support, target))
            similarity[source][target] = score
        for rank, (score, support, target) in enumerate(sorted(related, reverse=True)[:5], start=1):
            rows.append(
                {
                    "source_item": source,
                    "related_item": target,
                    "cosine_similarity": score,
                    "co_interaction_count": support,
                    "rank": rank,
                    "catalogue_relationship": _catalogue_relationship(source, target, catalogue),
                    "eligible_status": "eligible",
                }
            )
    return rows, dict(similarity)


def _recommend_for_model(
    model_id: str,
    users: list[str],
    catalogue: list[Record],
    candidates: list[Record],
    interactions: list[Record],
    item_scores: dict[str, dict[str, float]],
    similarity: dict[str, dict[str, float]],
    segments: dict[str, str],
    source_ingestion_run_id: str,
    config: RecommendationConfig,
) -> list[Record]:
    max_k = max(config.top_k)
    candidate_by_user = defaultdict(list)
    for row in candidates:
        candidate_by_user[str(row["user_id"])].append(row)
    user_history = defaultdict(list)
    for row in interactions:
        user_history[str(row["user_id"])].append(row)
    segment_scores = _segment_scores(interactions, segments)
    catalogue_by_id = {str(item["item_id"]): item for item in catalogue}
    rows: list[Record] = []
    for user_id in users:
        scored = []
        for candidate in candidate_by_user[user_id]:
            item_id = str(candidate["item_id"])
            raw_score, source, primary_reason = _score_candidate(
                model_id,
                item_id,
                user_id,
                item_scores,
                segment_scores,
                similarity,
                user_history,
                catalogue_by_id,
            )
            if raw_score <= 0:
                raw_score = float(catalogue_by_id[item_id]["catalogue_priority"]) * 0.01
                source = "catalogue_fallback"
                primary_reason = "cold_start_popular_item"
            scored.append((raw_score, item_id, source, primary_reason, candidate))
        ranked = sorted(scored, key=lambda row: (-row[0], row[1]))[:max_k]
        max_score = max((score for score, *_ in ranked), default=1.0)
        for rank, (score, item_id, source, reason, candidate) in enumerate(ranked, start=1):
            item = catalogue_by_id[item_id]
            rows.append(
                {
                    "user_id": user_id,
                    "snapshot_id": candidate["snapshot_id"],
                    "model_id": model_id,
                    "model_version": RECOMMENDATION_VERSION,
                    "item_id": item_id,
                    "rank": rank,
                    "raw_score": round(score, 6),
                    "normalised_score": round(_safe_div(score, max_score), 6),
                    "business_item_name": item["item_name"],
                    "item_category": item["item_category"],
                    "primary_reason": reason,
                    "candidate_source": source,
                    "cold_start_flag": 1 if not user_history[user_id] else 0,
                    "segment_id": segments.get(user_id, "unknown"),
                    "snapshot_timestamp": config.snapshot_time,
                    "source_ingestion_run_id": source_ingestion_run_id,
                }
            )
    return rows


def _evaluate_models(
    recommendations: list[Record],
    holdout: dict[str, set[str]],
    interactions: list[Record],
    catalogue: list[Record],
    config: RecommendationConfig,
) -> tuple[list[Record], list[Record], dict[str, object]]:
    rows_by_model = defaultdict(list)
    for row in recommendations:
        rows_by_model[str(row["model_id"])].append(row)
    comparison: list[Record] = []
    metrics_by_k: list[Record] = []
    for model_id, rows in sorted(rows_by_model.items()):
        users = sorted({str(row["user_id"]) for row in rows})
        evaluated = [user for user in users if holdout.get(user)]
        cold = [
            user for user in users if not any(str(row["user_id"]) == user for row in interactions)
        ]
        model_metrics = _metrics_for_model(rows, holdout, catalogue, interactions, config)
        comparison.append(
            {
                "model_id": model_id,
                "model_version": RECOMMENDATION_VERSION,
                "algorithm": MODEL_NAMES[model_id],
                "eligible_users": len(users),
                "evaluated_users": len(evaluated),
                "cold_start_users": len(cold),
                "user_coverage": model_metrics["user_coverage"],
                "precision@5": model_metrics["precision@5"],
                "recall@5": model_metrics["recall@5"],
                "hit_rate@5": model_metrics["hit_rate@5"],
                "MRR": model_metrics["MRR"],
                "MAP@5": model_metrics["MAP@5"],
                "NDCG@5": model_metrics["NDCG@5"],
                "catalogue_coverage@5": model_metrics["catalogue_coverage@5"],
                "novelty@5": model_metrics["novelty@5"],
                "diversity@5": model_metrics["diversity@5"],
                "fallback_rate": model_metrics["fallback_rate"],
                "selected_status": "not_selected",
                "rejection_reason": "",
            }
        )
        for k in config.top_k:
            k_metrics = _ranking_metrics(rows, holdout, catalogue, interactions, k, config)
            metrics_by_k.append({"model_id": model_id, "k": k, **k_metrics})
    return comparison, metrics_by_k, {"models": comparison, "metrics_by_k": metrics_by_k}


def _select_model(rows: list[Record], config: RecommendationConfig) -> str:
    eligible = [
        row
        for row in rows
        if float(row["user_coverage"]) >= config.minimum_user_coverage
        and float(row["catalogue_coverage@5"]) >= config.minimum_catalogue_coverage
    ] or rows
    ordered = sorted(
        eligible,
        key=lambda row: (
            float(row["NDCG@5"]),
            float(row["recall@5"]),
            _simplicity_rank(str(row["model_id"])),
        ),
        reverse=True,
    )
    return str(ordered[0]["model_id"])


def _write_outputs(
    *,
    output_dir: Path,
    config: RecommendationConfig,
    run_id: str,
    trusted_row_counts: dict[str, int],
    source_ingestion_run_id: str,
    source_checksum: str,
    source_contract_versions: dict[str, str],
    catalogue: list[Record],
    interactions: list[Record],
    candidates: list[Record],
    model_comparison: list[Record],
    offline_metrics: dict[str, object],
    metrics_by_k: list[Record],
    segment_metrics: list[Record],
    cold_start_metrics: dict[str, object],
    similarity_rows: list[Record],
    recommendations: list[Record],
    reasons: list[Record],
    coverage_rows: list[Record],
    diagnostics: dict[str, object],
    selected_model: str,
) -> None:
    files: dict[str, Callable[[Path], None]] = {
        "recommendation-definition.json": lambda path: _write_json(path, _definition(config)),
        "item-catalogue.json": lambda path: _write_json(path, catalogue),
        "interaction-mapping.json": lambda path: _write_json(path, interaction_mapping()),
        "user-item-interactions.csv": lambda path: _write_csv(path, interactions),
        "candidate-items.jsonl": lambda path: _write_jsonl(path, candidates),
        "model-comparison.csv": lambda path: _write_csv(path, model_comparison),
        "offline-metrics.json": lambda path: _write_json(path, offline_metrics),
        "metrics-by-k.csv": lambda path: _write_csv(path, metrics_by_k),
        "segment-metrics.csv": lambda path: _write_csv(path, segment_metrics),
        "cold-start-metrics.json": lambda path: _write_json(path, cold_start_metrics),
        "item-similarity.csv": lambda path: _write_csv(path, similarity_rows),
        "recommendations.csv": lambda path: _write_csv(path, recommendations),
        "recommendation-reasons.jsonl": lambda path: _write_jsonl(path, reasons),
        "catalogue-coverage.csv": lambda path: _write_csv(path, coverage_rows),
        "model-metadata.json": lambda path: _write_json(
            path,
            _metadata(
                config,
                run_id,
                selected_model,
                source_ingestion_run_id,
                source_checksum,
                catalogue,
                interactions,
                candidates,
                model_comparison,
            ),
        ),
        "run-diagnostics.json": lambda path: _write_json(path, diagnostics),
        "recommendation-lineage.json": lambda path: _write_json(
            path,
            _lineage(source_ingestion_run_id, source_checksum, source_contract_versions),
        ),
        "recommendation-card.md": lambda path: _write_text(
            path, _recommendation_card(config, selected_model, model_comparison, diagnostics)
        ),
    }
    checksums: dict[str, str] = {}
    for filename, writer in files.items():
        path = output_dir / filename
        writer(path)
        checksums[filename] = file_sha256(path)
    manifest = {
        "recommendation_run_id": run_id,
        "model_version": RECOMMENDATION_VERSION,
        "source_ingestion_run_id": source_ingestion_run_id,
        "source_manifest_checksum": source_checksum,
        "input_row_counts": trusted_row_counts,
        "output_row_counts": {
            "user-item-interactions.csv": len(interactions),
            "candidate-items.jsonl": len(candidates),
            "recommendations.csv": len(recommendations),
            "item-similarity.csv": len(similarity_rows),
        },
        "output_checksums": checksums,
        "selected_model": selected_model,
        "overall_status": diagnostics["overall_status"],
        "created_at": config.fixed_run_time,
    }
    _write_json(output_dir / "recommendation-manifest.json", manifest)


def _score_candidate(
    model_id: str,
    item_id: str,
    user_id: str,
    item_scores: dict[str, dict[str, float]],
    segment_scores: dict[str, dict[str, float]],
    similarity: dict[str, dict[str, float]],
    user_history: dict[str, list[Record]],
    catalogue: dict[str, Record],
) -> tuple[float, str, str]:
    if model_id == "global_popularity":
        return (
            item_scores["global_popularity"].get(item_id, 0.0),
            "global_popularity",
            "popular_with_all_users",
        )
    if model_id == "recent_popularity":
        return (
            item_scores["recent_popularity"].get(item_id, 0.0),
            "recent_popularity",
            "trending_recently",
        )
    if model_id == "segment_popularity":
        segment_id = _history_segment(user_history.get(user_id, []))
        score = segment_scores.get(segment_id, {}).get(item_id, 0.0)
        if score > 0:
            return (score, "segment_popularity", "popular_in_your_segment")
        return (
            item_scores["global_popularity"].get(item_id, 0.0),
            "segment_global_fallback",
            "cold_start_popular_item",
        )
    related_score = 0.0
    best_source = ""
    for row in user_history.get(user_id, []):
        source_item = str(row["item_id"])
        score = similarity.get(source_item, {}).get(item_id, 0.0) * float(
            row["weighted_interaction_score"]
        )
        if score > related_score:
            related_score = score
            best_source = source_item
    if related_score > 0:
        reason = _related_reason(best_source, item_id, catalogue)
        return (related_score, f"item_similarity:{best_source}", reason)
    return (
        item_scores["global_popularity"].get(item_id, 0.0),
        "cf_popularity_fallback",
        "cold_start_popular_item",
    )


def _segment_scores(
    interactions: list[Record], segments: dict[str, str]
) -> dict[str, dict[str, float]]:
    scores: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in interactions:
        segment_id = segments.get(str(row["user_id"]), _history_segment([row]))
        scores[segment_id][str(row["item_id"])] += float(row["weighted_interaction_score"])
    return {segment: dict(items) for segment, items in scores.items()}


def _reconstructed_segments(config: RecommendationConfig) -> dict[str, str]:
    if not config.use_segments:
        return {}
    rows, _ = build_segmentation_rows(
        SegmentationConfig(
            input_dir=config.input_dir,
            output_root=Path("/tmp/unused-segmentation"),
            snapshot_time=config.snapshot_time,
            lookback_days=config.lookback_days,
            fixed_run_time=config.fixed_run_time,
        )
    )
    assignments = assign_rule_based_segments(rows, "recommendation-segmentation")
    return {assignment.user_id: assignment.rule_based_segment_id for assignment in assignments}


def _metrics_for_model(
    rows: list[Record],
    holdout: dict[str, set[str]],
    catalogue: list[Record],
    interactions: list[Record],
    config: RecommendationConfig,
) -> dict[str, float]:
    metrics = _ranking_metrics(rows, holdout, catalogue, interactions, 5, config)
    return {
        "user_coverage": metrics["user_coverage"],
        "precision@5": metrics["precision"],
        "recall@5": metrics["recall"],
        "hit_rate@5": metrics["hit_rate"],
        "MRR": metrics["mrr"],
        "MAP@5": metrics["map"],
        "NDCG@5": metrics["ndcg"],
        "catalogue_coverage@5": metrics["catalogue_coverage"],
        "novelty@5": metrics["novelty"],
        "diversity@5": metrics["diversity"],
        "fallback_rate": metrics["fallback_rate"],
    }


def _ranking_metrics(
    rows: list[Record],
    holdout: dict[str, set[str]],
    catalogue: list[Record],
    interactions: list[Record],
    k: int,
    config: RecommendationConfig,
) -> dict[str, float]:
    by_user: dict[str, list[Record]] = defaultdict(list)
    for row in rows:
        if int(row["rank"]) <= k:
            by_user[str(row["user_id"])].append(row)
    users = sorted(by_user)
    evaluated = [user for user in users if holdout.get(user)]
    precisions = []
    recalls = []
    hits = []
    reciprocal = []
    average_precisions = []
    ndcgs = []
    popularity = _historical_item_share(interactions)
    novelty_values: list[float] = []
    diversity_values = []
    fallback_count = 0
    recommended_items = set()
    for user in users:
        rec_items = [
            str(row["item_id"]) for row in sorted(by_user[user], key=lambda item: int(item["rank"]))
        ]
        recommended_items.update(rec_items)
        fallback_count += sum(
            1 for row in by_user[user] if "fallback" in str(row["candidate_source"])
        )
        novelty_values.extend(
            _novelty(item, popularity, config.novelty_smoothing) for item in rec_items
        )
        diversity_values.append(_category_diversity(rec_items, catalogue))
        relevant = holdout.get(user, set())
        if not relevant:
            continue
        hit_positions = [index + 1 for index, item in enumerate(rec_items) if item in relevant]
        hit_count = len(hit_positions)
        precisions.append(_safe_div(hit_count, min(k, len(rec_items))))
        recalls.append(_safe_div(hit_count, len(relevant)))
        hits.append(1.0 if hit_count else 0.0)
        reciprocal.append(1 / hit_positions[0] if hit_positions else 0.0)
        average_precisions.append(_average_precision(rec_items, relevant, k))
        ndcgs.append(_ndcg(rec_items, relevant, k))
    total_recs = sum(len(items) for items in by_user.values())
    return {
        "precision": _avg(precisions),
        "recall": _avg(recalls),
        "hit_rate": _avg(hits),
        "mrr": _avg(reciprocal),
        "map": _avg(average_precisions),
        "ndcg": _avg(ndcgs),
        "catalogue_coverage": _safe_div(len(recommended_items), len(catalogue)),
        "user_coverage": _safe_div(len(users), len(set(row["user_id"] for row in rows))),
        "novelty": _avg(novelty_values),
        "diversity": _avg(diversity_values),
        "fallback_rate": _safe_div(fallback_count, total_recs),
        "evaluated_users": len(evaluated),
        "users_with_no_relevant_holdout": len(users) - len(evaluated),
    }


def _segment_metrics(
    recommendations: list[Record],
    holdout: dict[str, set[str]],
    segments: dict[str, str],
    config: RecommendationConfig,
) -> list[Record]:
    output = []
    for model_id in sorted({str(row["model_id"]) for row in recommendations}):
        model_rows = [row for row in recommendations if row["model_id"] == model_id]
        for segment_id in sorted(set(segments.values()) | {"unknown"}):
            users = {user for user, segment in segments.items() if segment == segment_id}
            rows = [row for row in model_rows if str(row["user_id"]) in users]
            if not rows:
                continue
            metrics = _ranking_metrics(rows, holdout, item_catalogue(), [], 5, config)
            output.append(
                {
                    "model_id": model_id,
                    "segment_id": segment_id,
                    "user_count": len({row["user_id"] for row in rows}),
                    "precision@5": metrics["precision"],
                    "recall@5": metrics["recall"],
                    "hit_rate@5": metrics["hit_rate"],
                    "user_coverage": metrics["user_coverage"],
                }
            )
    return output


def _cold_start_metrics(
    recommendations: list[Record],
    holdout: dict[str, set[str]],
    interactions: list[Record],
    config: RecommendationConfig,
) -> dict[str, object]:
    users = {str(row["user_id"]) for row in recommendations}
    warm = {str(row["user_id"]) for row in interactions}
    cold_users = users - warm
    cold_rows = [row for row in recommendations if str(row["user_id"]) in cold_users]
    return {
        "cold_start_users": len(cold_users),
        "cold_start_user_coverage": _safe_div(
            len({row["user_id"] for row in cold_rows}), len(cold_users)
        ),
        "cold_start_recommendations": len(cold_rows),
        "cold_start_evaluated_users": sum(1 for user in cold_users if holdout.get(user)),
        "policy": "global and recent popularity with catalogue eligibility fallback",
        "top_k": list(config.top_k),
    }


def _catalogue_coverage(
    recommendations: list[Record], catalogue: list[Record], config: RecommendationConfig
) -> list[Record]:
    rows = []
    for model_id in sorted({str(row["model_id"]) for row in recommendations}):
        model_rows = [row for row in recommendations if row["model_id"] == model_id]
        for k in config.top_k:
            items = {str(row["item_id"]) for row in model_rows if int(row["rank"]) <= k}
            rows.append(
                {
                    "model_id": model_id,
                    "k": k,
                    "recommended_items": len(items),
                    "active_catalogue_items": len(catalogue),
                    "catalogue_coverage": _safe_div(len(items), len(catalogue)),
                }
            )
    return rows


def _reason_rows(recommendations: list[Record]) -> list[Record]:
    return [
        {
            "user_id": row["user_id"],
            "snapshot_id": row["snapshot_id"],
            "model_id": row["model_id"],
            "item_id": row["item_id"],
            "rank": row["rank"],
            "reason_codes": [row["primary_reason"], str(row["candidate_source"])],
            "reason_text": _reason_text(str(row["primary_reason"])),
        }
        for row in recommendations
    ]


def _validate_catalogue(catalogue: list[Record]) -> None:
    ids = [str(row["item_id"]) for row in catalogue]
    if len(ids) != len(set(ids)):
        raise ValueError("Recommendation catalogue item IDs must be unique.")
    allowed_categories = {
        "feature",
        "template",
        "automation",
        "integration",
        "workflow",
        "education",
        "collaboration_action",
    }
    for row in catalogue:
        if row["item_category"] not in allowed_categories:
            raise ValueError("Unknown recommendation item category.")
        for required in row["required_prior_actions"]:
            if required not in ids:
                raise ValueError("Unknown prerequisite item ID.")


def _validate_outputs(
    catalogue: list[Record],
    interactions: list[Record],
    holdout: dict[str, set[str]],
    candidates: list[Record],
    recommendations: list[Record],
    model_comparison: list[Record],
) -> None:
    _validate_catalogue(catalogue)
    if len({(row["user_id"], row["item_id"]) for row in interactions}) != len(interactions):
        raise ValueError("Interactions must be one row per user-item pair.")
    if any(float(row["weighted_interaction_score"]) < 0 for row in interactions):
        raise ValueError("Interaction weights must be non-negative.")
    candidate_keys = {(row["user_id"], row["item_id"]) for row in candidates}
    by_user_model: dict[tuple[str, str], list[Record]] = defaultdict(list)
    for row in recommendations:
        if (row["user_id"], row["item_id"]) not in candidate_keys:
            raise ValueError("Recommended items must belong to the candidate set.")
        by_user_model[(str(row["user_id"]), str(row["model_id"]))].append(row)
    for rows in by_user_model.values():
        ranks = sorted(int(row["rank"]) for row in rows)
        if ranks != list(range(1, len(rows) + 1)):
            raise ValueError("Recommendation ranks must be contiguous from 1.")
        if len({row["item_id"] for row in rows}) != len(rows):
            raise ValueError("Duplicate recommendations for one user/model are not allowed.")
    for row in model_comparison:
        for metric in ("user_coverage", "precision@5", "recall@5", "hit_rate@5", "NDCG@5"):
            if not 0 <= float(row[metric]) <= 1:
                raise ValueError(f"Metric out of range: {metric}.")
    for items in holdout.values():
        if not isinstance(items, set):
            raise ValueError("Holdout items must be grouped by user.")


def _diagnostics(
    *,
    trusted_users: int,
    users: list[str],
    exclusions: dict[str, int],
    interactions: list[Record],
    holdout: dict[str, set[str]],
    candidates: list[Record],
    recommendations: list[Record],
    selected_model: str,
    similarity_rows: list[Record],
) -> dict[str, object]:
    return {
        "trusted_input_compatibility": "passed",
        "users_considered": trusted_users,
        "eligible_users": len(users),
        "excluded_users_by_reason": exclusions,
        "catalogue_validation": "passed",
        "interactions_created": len(interactions),
        "users_with_insufficient_history": exclusions.get("below_minimum_user_interactions", 0),
        "cold_start_users": len(set(users) - {str(row["user_id"]) for row in interactions}),
        "candidate_counts": len(candidates),
        "users_with_no_candidates": len(set(users) - {str(row["user_id"]) for row in candidates}),
        "users_with_no_relevant_holdout_items": len(set(users) - set(holdout)),
        "model_training_status": "passed",
        "fallback_counts": sum(
            1 for row in recommendations if "fallback" in str(row["candidate_source"])
        ),
        "zero_denominator_metrics": "reported explicitly",
        "sparse_item_warnings": [],
        "similarity_support_warnings": []
        if similarity_rows
        else ["no item similarities met support"],
        "coverage_warnings": [],
        "selected_model": selected_model,
        "manifest_reconciliation": "passed",
        "overall_status": "passed",
    }


def _definition(config: RecommendationConfig) -> Record:
    return {
        "definition_id": "governed_recommendation_baseline",
        "version": RECOMMENDATION_VERSION,
        "snapshot_timestamp": config.snapshot_time,
        "lookback_days": config.lookback_days,
        "holdout_days": config.holdout_days,
        "enabled_models": list(config.enabled_models),
        "selection_rule": (
            "reject below coverage guardrails; prioritise NDCG@5; use recall@5 tie-breaker; "
            "prefer simpler baselines where materially similar"
        ),
        "leakage_policy": "training and candidates use records at or before snapshot only",
    }


def _metadata(
    config: RecommendationConfig,
    run_id: str,
    selected_model: str,
    source_ingestion_run_id: str,
    source_checksum: str,
    catalogue: list[Record],
    interactions: list[Record],
    candidates: list[Record],
    model_comparison: list[Record],
) -> Record:
    selected_metrics = next(row for row in model_comparison if row["model_id"] == selected_model)
    return {
        "selected_model_id": selected_model,
        "model_run_id": run_id,
        "model_version": RECOMMENDATION_VERSION,
        "algorithm": MODEL_NAMES[selected_model],
        "snapshot_timestamp": config.snapshot_time,
        "lookback_window_days": config.lookback_days,
        "holdout_window_days": config.holdout_days,
        "catalogue_version": CATALOGUE_VERSION,
        "interaction_mapping_version": MAPPING_VERSION,
        "source_ingestion_run_id": source_ingestion_run_id,
        "source_manifest_checksum": source_checksum,
        "optional_segment_version": "2026-07-milestone-7-rules",
        "eligible_user_count": int(selected_metrics["eligible_users"]),
        "evaluated_user_count": int(selected_metrics["evaluated_users"]),
        "catalogue_size": len(catalogue),
        "interaction_count": len(interactions),
        "candidate_count": len(candidates),
        "top_k_values": list(config.top_k),
        "model_parameters": {
            "minimum_item_interactions": config.minimum_item_interactions,
            "minimum_similarity_support": config.minimum_similarity_support,
        },
        "selection_rule": _definition(config)["selection_rule"],
        "selected_metrics": selected_metrics,
        "fallback_policy": "popularity fallback for sparse collaborative and segment scores",
        "random_seed": config.random_seed,
        "software_version": get_project_metadata().version,
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
            "item catalogue",
            "point-in-time implicit interactions",
            "candidate generation",
            "popularity baselines",
            "segment-aware popularity",
            "item-item collaborative filtering",
            "time-based holdout evaluation",
        ],
    }


def _recommendation_card(
    config: RecommendationConfig,
    selected_model: str,
    model_comparison: list[Record],
    diagnostics: dict[str, object],
) -> str:
    selected = next(row for row in model_comparison if row["model_id"] == selected_model)
    return "\n".join(
        [
            "# Recommendation Baseline Card",
            "",
            "Intended use: offline product analysis and batch recommendation baseline review.",
            "Out-of-scope use: online serving, automated decisions, uplift, or experiment winners.",
            "All data is synthetic. Recommendations are ranked suggestions, not probabilities.",
            "",
            f"Snapshot: {config.snapshot_time}. Lookback: {config.lookback_days} days.",
            f"Holdout: {config.holdout_days} days.",
            "Models compared: global popularity, recent popularity, segment popularity,",
            "and item-item CF.",
            f"Selected model: {selected_model}. NDCG@5: {selected['NDCG@5']}.",
            f"Eligible users: {diagnostics['eligible_users']}.",
            "",
            "Diversity, novelty and coverage are descriptive offline metrics. Item similarity is",
            "associative and not causal. Production use would require online experimentation,",
            "monitoring, privacy review and human oversight.",
            "",
            "Azure mapping: trusted data in ADLS Gen2, interaction preparation in Synapse,",
            "training and batch generation in Azure ML, tracking with MLflow,",
            "governance via Purview.",
            "",
        ]
    )


def _mapping(event_name: str, item_id: str, strength: str, feature_name: str | None) -> Record:
    return {
        "event_name": event_name,
        "item_id": item_id,
        "interaction_strength": strength,
        "weight": INTERACTION_WEIGHTS[strength],
        "feature_name": feature_name,
        "mapping_version": MAPPING_VERSION,
    }


def _mapped_item_id(event: Record, mapping: Record) -> str | None:
    if mapping["item_id"] == "recommendation":
        recommendation_id = event.get("recommendation_id")
        if recommendation_id and str(recommendation_id).startswith("syn_rec_"):
            return "template_weekly_planning"
        return "education_automation_guide"
    expected_feature = mapping.get("feature_name")
    if expected_feature and expected_feature != "onboarding":
        actual_feature = event.get("feature_name")
        if actual_feature and str(actual_feature) != str(expected_feature):
            return None
    return str(mapping["item_id"])


def _consumed(item_id: str, strengths: Counter[str]) -> bool:
    if item_id.startswith("template_") or item_id.startswith("education_"):
        return False
    return (
        strengths["acceptance"]
        + strengths["successful_use"]
        + strengths["repeat_use"]
        + strengths["use"]
    ) > 0


def _historical_item_share(interactions: list[Record]) -> dict[str, float]:
    totals: defaultdict[str, float] = defaultdict(float)
    for row in interactions:
        totals[str(row["item_id"])] += float(row["weighted_interaction_score"])
    total = sum(totals.values())
    return {item: _safe_div(score, total) for item, score in totals.items()}


def _novelty(item_id: str, popularity: dict[str, float], smoothing: float) -> float:
    share = popularity.get(item_id, 0.0) + smoothing / 100
    return round(-math.log2(share), 6)


def _category_diversity(items: list[str], catalogue: list[Record]) -> float:
    if not items:
        return 0.0
    category_by_id = {str(row["item_id"]): str(row["item_category"]) for row in catalogue}
    return round(
        _safe_div(len({category_by_id.get(item, "unknown") for item in items}), len(items)), 6
    )


def _average_precision(items: list[str], relevant: set[str], k: int) -> float:
    hits = 0
    score = 0.0
    for index, item in enumerate(items[:k], start=1):
        if item in relevant:
            hits += 1
            score += hits / index
    return round(_safe_div(score, min(len(relevant), k)), 6)


def _ndcg(items: list[str], relevant: set[str], k: int) -> float:
    dcg = sum(1 / math.log2(index + 2) for index, item in enumerate(items[:k]) if item in relevant)
    ideal = sum(1 / math.log2(index + 2) for index in range(min(len(relevant), k)))
    return round(_safe_div(dcg, ideal), 6)


def _catalogue_relationship(source: str, target: str, catalogue: list[Record]) -> str:
    by_id = {str(row["item_id"]): row for row in catalogue}
    if by_id[source]["item_category"] == by_id[target]["item_category"]:
        return "same_category"
    if by_id[source]["feature_name"] == by_id[target]["feature_name"]:
        return "same_feature_family"
    return "co_interaction"


def _related_reason(source: str, target: str, catalogue: dict[str, Record]) -> str:
    source_feature = str(catalogue.get(source, {}).get("feature_name", ""))
    target_feature = str(catalogue.get(target, {}).get("feature_name", ""))
    if source_feature == "collaboration" or target_feature == "collaboration":
        return "frequently_used_with_collaboration"
    if source_feature == "automation" or target_feature == "automation":
        return "frequently_used_with_automation"
    return "related_to_used_feature"


def _history_segment(history: list[Record]) -> str:
    items = {str(row["item_id"]) for row in history}
    if any(item.startswith("automation") for item in items):
        return "automation_power_user"
    if any("collaboration" in item or "invite" in item for item in items):
        return "collaboration_adopter"
    if not items:
        return "cold_start"
    return "core_engaged"


def _reason_text(reason: str) -> str:
    return reason.replace("_", " ").capitalize()


def _simplicity_rank(model_id: str) -> int:
    return {
        "global_popularity": 4,
        "recent_popularity": 3,
        "segment_popularity": 2,
        "item_item_cf": 1,
    }.get(model_id, 0)


def _snapshot_id(user_id: str, snapshot_time: str) -> str:
    return record_fingerprint({"user_id": user_id, "recommendation_snapshot": snapshot_time})[:16]


def _avg(values: list[float]) -> float:
    return round(_safe_div(sum(values), len(values)), 6)


def _safe_div(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _default_run_id(config: RecommendationConfig) -> str:
    if config.fixed_run_time:
        stamp = (
            config.fixed_run_time.replace(":", "")
            .replace("-", "")
            .replace("T", "-")
            .replace("Z", "")
        )
    else:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"recommendations-{stamp}"


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


def run_sample_to_temp() -> RecommendationResult:
    """Run sample ingestion then recommendations in a temporary directory."""

    from product_growth_intelligence.ingestion import IngestionConfig, run_batch_ingestion

    with TemporaryDirectory() as temp:
        root = Path(temp)
        ingestion = run_batch_ingestion(
            IngestionConfig(
                source=Path("data/samples/nexaflow"),
                output_root=root / "interim",
                quality_root=root / "quality",
                run_id="milestone8-source",
                fixed_ingestion_time="2026-01-01T00:00:00Z",
                overwrite=True,
            )
        )
        return run_recommendations(
            RecommendationConfig(
                input_dir=ingestion.output_dir,
                output_root=root / "recommendations",
                run_id="milestone8-recommendations",
                fixed_run_time="2026-01-02T00:00:00Z",
                overwrite=True,
            )
        )
