"""Leakage-aware churn feature, training and evaluation pipeline."""

# ruff: noqa: ANN401

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import numpy as np
from sklearn.compose import ColumnTransformer  # type: ignore[import-untyped]
from sklearn.ensemble import RandomForestClassifier  # type: ignore[import-untyped]
from sklearn.impute import SimpleImputer  # type: ignore[import-untyped]
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
from sklearn.metrics import (  # type: ignore[import-untyped]
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    log_loss,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline  # type: ignore[import-untyped]
from sklearn.preprocessing import OneHotEncoder, StandardScaler  # type: ignore[import-untyped]

from product_growth_intelligence.analytics.inputs import (
    dataset_row_counts,
    load_trusted_input,
    source_manifest_checksum,
)
from product_growth_intelligence.analytics.retention.definitions import DEFAULT_QUALIFYING_EVENTS
from product_growth_intelligence.data_generation.models import JsonValue, Record
from product_growth_intelligence.ingestion.fingerprints import file_sha256, record_fingerprint
from product_growth_intelligence.metadata import get_project_metadata
from product_growth_intelligence.models.churn.models import (
    ChurnTrainingConfig,
    ChurnTrainingResult,
    FeatureRow,
    SnapshotLabel,
)

CHURN_VERSION = "2026-07-milestone-6"
NUMERIC_FEATURES = (
    "account_age_days",
    "sessions_in_lookback",
    "active_days_in_lookback",
    "qualifying_events_in_lookback",
    "events_per_active_day",
    "average_session_duration_seconds",
    "days_since_last_qualifying_activity",
    "active_day_proportion",
    "recent_sessions",
    "prior_sessions",
    "session_delta",
    "recent_qualifying_events",
    "prior_qualifying_events",
    "event_delta",
    "distinct_features_used",
    "collaboration_actions",
    "automation_actions",
    "search_actions",
    "task_completion_events",
    "recommendation_interactions",
    "feature_errors",
    "failed_requests",
    "feature_usage_errors",
    "error_rate",
    "days_on_current_plan",
    "mrr_at_snapshot",
    "prior_subscription_changes",
    "historical_active_days",
    "longest_inactivity_gap_days",
)
CATEGORICAL_FEATURES = (
    "country",
    "region",
    "acquisition_channel",
    "device_preference",
    "persona",
    "company_size_band",
    "initial_plan",
    "marketing_consent",
    "is_team_account",
    "plan_at_snapshot",
    "billing_cycle_at_snapshot",
    "subscription_status_at_snapshot",
    "activated_before_snapshot",
    "paid_before_snapshot",
)
FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES


class ConstantProbabilityModel:
    """Tiny sklearn-like estimator used for the deterministic baseline."""

    def __init__(self, probability: float) -> None:
        self.probability = min(max(probability, 0.0), 1.0)

    def predict_proba(self, rows: list[Record]) -> np.ndarray[Any, Any]:
        """Return a two-column probability matrix."""

        return np.array([[1.0 - self.probability, self.probability] for _ in rows])


def run_churn_training(config: ChurnTrainingConfig) -> ChurnTrainingResult:
    """Run deterministic churn training over trusted accepted inputs."""

    config.validate()
    trusted = load_trusted_input(config.input_dir)
    run_id = config.run_id or _default_run_id(config)
    output_dir = config.output_root / run_id
    if output_dir.exists() and any(output_dir.iterdir()) and not config.overwrite:
        msg = f"Output directory {output_dir} already exists and is not empty. Pass --overwrite."
        raise FileExistsError(msg)
    if config.validate_only:
        return ChurnTrainingResult(
            run_id=run_id,
            status="validated",
            output_dir=output_dir,
            row_count=0,
            selected_model="none",
            selected_threshold=0.5,
            label_prevalence=0.0,
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    rows = build_feature_rows(config)
    if len(rows) < 3:
        msg = "Churn training requires at least three complete snapshots."
        raise ValueError(msg)

    splits = _chronological_splits(rows, config.lookback_days, config.label_window_days)
    train_rows = [row for row, split in zip(rows, splits, strict=True) if split["split"] == "train"]
    validation_rows = [
        row for row, split in zip(rows, splits, strict=True) if split["split"] == "validation"
    ]
    test_rows = [row for row, split in zip(rows, splits, strict=True) if split["split"] == "test"]
    candidates = _train_candidates(train_rows, config)
    selection = _select_model(candidates, validation_rows, config)
    selected_model_name = str(selection["model_name"])
    selected_model = selection["model"]
    validation_probabilities = _probabilities(selected_model, validation_rows)
    threshold_rows = _threshold_rows(validation_rows, validation_probabilities)
    selected_threshold = _select_threshold(threshold_rows, validation_probabilities, config)
    test_probabilities = _probabilities(selected_model, test_rows)

    training_metrics: dict[str, object] = {
        name: _evaluate(train_rows, _probabilities(model, train_rows), selected_threshold)
        for name, model in candidates.items()
    }
    validation_metrics = _evaluate(validation_rows, validation_probabilities, selected_threshold)
    test_metrics = _evaluate(test_rows, test_probabilities, selected_threshold)
    predictions = _prediction_rows(test_rows, test_probabilities, selected_threshold)
    feature_importance = _feature_importance(selected_model, selected_model_name)
    diagnostics = _diagnostics(rows, splits, config, validation_metrics, test_metrics)

    _write_all(
        output_dir=output_dir,
        config=config,
        run_id=run_id,
        trusted_row_counts=dataset_row_counts(trusted),
        source_checksum=source_manifest_checksum(config.input_dir),
        source_ingestion_run_id=trusted.source_ingestion_run_id,
        contract_versions=trusted.contract_versions,
        rows=rows,
        splits=splits,
        training_metrics=training_metrics,
        validation_metrics=validation_metrics,
        test_metrics=test_metrics,
        threshold_rows=threshold_rows,
        predictions=predictions,
        feature_importance=feature_importance,
        diagnostics=diagnostics,
        selected_model=selected_model_name,
        selected_threshold=selected_threshold,
    )
    return ChurnTrainingResult(
        run_id=run_id,
        status=str(diagnostics["overall_status"]),
        output_dir=output_dir,
        row_count=len(rows),
        selected_model=selected_model_name,
        selected_threshold=selected_threshold,
        label_prevalence=round(sum(row.label.behavioural_churn for row in rows) / len(rows), 6),
        validation_metrics=validation_metrics,
        test_metrics=test_metrics,
    )


def build_feature_rows(config: ChurnTrainingConfig) -> list[FeatureRow]:
    """Build point-in-time feature rows and future labels."""

    trusted = load_trusted_input(config.input_dir)
    analysis_start = _parse_dt(config.analysis_start)
    analysis_end = _parse_dt(config.analysis_end)
    users = sorted(trusted.datasets["users"], key=lambda row: str(row["user_id"]))
    sessions_by_user = _records_by_user(trusted.datasets["sessions"])
    events_by_user = _records_by_user(trusted.datasets["clickstream_events"])
    usage_by_user = _records_by_user(trusted.datasets["feature_usage"])
    subscriptions_by_user = _records_by_user(trusted.datasets["subscriptions"])
    rows: list[FeatureRow] = []
    for user in users:
        user_id = str(user["user_id"])
        signup = _parse_dt(str(user["signup_timestamp"]))
        snapshot = max(signup + timedelta(days=config.lookback_days), analysis_start)
        label_end = snapshot + timedelta(days=config.label_window_days)
        if snapshot > analysis_end or label_end > analysis_end:
            continue
        feature_start = snapshot - timedelta(days=config.lookback_days)
        label = _label(
            user_id,
            snapshot,
            feature_start,
            label_end,
            events_by_user[user_id],
            subscriptions_by_user[user_id],
            _plan_at_snapshot(subscriptions_by_user[user_id], snapshot),
        )
        rows.append(
            FeatureRow(
                label=label,
                features=_features(
                    user,
                    snapshot,
                    feature_start,
                    sessions_by_user[user_id],
                    events_by_user[user_id],
                    usage_by_user[user_id],
                    subscriptions_by_user[user_id],
                ),
            )
        )
    return sorted(rows, key=lambda row: (row.label.snapshot_timestamp, row.label.user_id))


def _label(
    user_id: str,
    snapshot: datetime,
    feature_start: datetime,
    label_end: datetime,
    events: list[Record],
    subscriptions: list[Record],
    plan_at_snapshot: str,
) -> SnapshotLabel:
    future_events = [
        event
        for event in events
        if snapshot < _parse_dt(str(event["event_timestamp"])) <= label_end
        and str(event["event_name"]) in DEFAULT_QUALIFYING_EVENTS
    ]
    future_subs = [
        sub
        for sub in subscriptions
        if snapshot < _parse_dt(str(sub["period_start_timestamp"])) <= label_end
    ]
    downgraded = any(
        _plan_rank(str(sub["plan_name"])) < _plan_rank(plan_at_snapshot) for sub in future_subs
    )
    cancelled = any(
        str(sub.get("status", "")).lower() in {"cancelled", "canceled"} for sub in future_subs
    )
    is_paid = _plan_rank(plan_at_snapshot) > 0
    churn = 1 if not future_events else 0
    return SnapshotLabel(
        snapshot_id=record_fingerprint({"user_id": user_id, "snapshot": _format_dt(snapshot)})[:16],
        user_id=user_id,
        snapshot_timestamp=_format_dt(snapshot),
        feature_window_start=_format_dt(feature_start),
        feature_window_end=_format_dt(snapshot),
        label_window_start=_format_dt(snapshot),
        label_window_end=_format_dt(label_end),
        behavioural_churn=churn,
        future_qualifying_events=len(future_events),
        subscription_cancelled=1 if cancelled else 0,
        subscription_downgraded=1 if downgraded else 0,
        paid_inactive=1 if is_paid and churn else 0,
        free_inactive=1 if not is_paid and churn else 0,
    )


def _features(
    user: Record,
    snapshot: datetime,
    feature_start: datetime,
    sessions: list[Record],
    events: list[Record],
    usage: list[Record],
    subscriptions: list[Record],
) -> Record:
    signup = _parse_dt(str(user["signup_timestamp"]))
    window_sessions = [
        session
        for session in sessions
        if feature_start <= _parse_dt(str(session["session_start_timestamp"])) <= snapshot
    ]
    window_events = [
        event
        for event in events
        if feature_start <= _parse_dt(str(event["event_timestamp"])) <= snapshot
    ]
    qualifying = [
        event for event in window_events if str(event["event_name"]) in DEFAULT_QUALIFYING_EVENTS
    ]
    active_days = {
        _parse_dt(str(event["event_timestamp"])).date().isoformat() for event in qualifying
    }
    midpoint = feature_start + (snapshot - feature_start) / 2
    recent_events = [
        event for event in qualifying if _parse_dt(str(event["event_timestamp"])) > midpoint
    ]
    prior_events = [
        event for event in qualifying if _parse_dt(str(event["event_timestamp"])) <= midpoint
    ]
    recent_sessions = [
        session
        for session in window_sessions
        if _parse_dt(str(session["session_start_timestamp"])) > midpoint
    ]
    prior_sessions = [
        session
        for session in window_sessions
        if _parse_dt(str(session["session_start_timestamp"])) <= midpoint
    ]
    last_event_at = max(
        (_parse_dt(str(event["event_timestamp"])) for event in qualifying), default=None
    )
    plan, cycle, status, mrr, days_on_plan = _subscription_context(subscriptions, snapshot)
    usage_window = [
        row
        for row in usage
        if feature_start.date()
        <= datetime.fromisoformat(str(row["observation_date"])).date()
        <= snapshot.date()
    ]
    historical_days = sorted(
        {
            _parse_dt(str(event["event_timestamp"])).date()
            for event in events
            if _parse_dt(str(event["event_timestamp"])) <= snapshot
        }
    )
    inactivity_gap = _longest_gap(historical_days)
    event_counts = Counter(str(event["event_name"]) for event in window_events)
    feature_names = {
        str(event.get("feature_name")) for event in window_events if event.get("feature_name")
    }
    feature_names.update(str(row["feature_name"]) for row in usage_window)
    return {
        "account_age_days": (snapshot - signup).days,
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
        "days_since_last_qualifying_activity": (
            (snapshot - last_event_at).days if last_event_at is not None else 999
        ),
        "active_day_proportion": _safe_div(
            len(active_days), max((snapshot - feature_start).days, 1)
        ),
        "recent_sessions": len(recent_sessions),
        "prior_sessions": len(prior_sessions),
        "session_delta": len(recent_sessions) - len(prior_sessions),
        "recent_qualifying_events": len(recent_events),
        "prior_qualifying_events": len(prior_events),
        "event_delta": len(recent_events) - len(prior_events),
        "distinct_features_used": len(feature_names),
        "collaboration_actions": _count_feature(window_events, usage_window, "collaboration"),
        "automation_actions": _count_feature(window_events, usage_window, "automation"),
        "search_actions": event_counts["search_performed"],
        "task_completion_events": event_counts["task_completed"],
        "recommendation_interactions": event_counts["recommendation_clicked"]
        + event_counts["recommendation_accepted"],
        "feature_errors": event_counts["feature_error"],
        "failed_requests": event_counts["request_failed"],
        "feature_usage_errors": sum(int(row.get("error_count", 0) or 0) for row in usage_window),
        "error_rate": _safe_div(
            event_counts["feature_error"]
            + event_counts["request_failed"]
            + sum(int(row.get("error_count", 0) or 0) for row in usage_window),
            len(window_events) + sum(int(row.get("usage_count", 0) or 0) for row in usage_window),
        ),
        "days_on_current_plan": days_on_plan,
        "mrr_at_snapshot": mrr,
        "prior_subscription_changes": sum(
            1
            for sub in subscriptions
            if _parse_dt(str(sub["period_start_timestamp"])) <= snapshot
            and str(sub.get("plan_name", "")) != str(user.get("initial_plan", ""))
        ),
        "historical_active_days": len(historical_days),
        "longest_inactivity_gap_days": inactivity_gap,
        "country": str(user.get("country", "unknown")),
        "region": str(user.get("region", "unknown")),
        "acquisition_channel": str(user.get("acquisition_channel", "unknown")),
        "device_preference": str(user.get("device_preference", "unknown")),
        "persona": str(user.get("persona", "unknown")),
        "company_size_band": str(user.get("company_size_band", "unknown")),
        "initial_plan": str(user.get("initial_plan", "unknown")),
        "marketing_consent": str(user.get("marketing_consent", "unknown")),
        "is_team_account": str(user.get("is_team_account", "unknown")),
        "plan_at_snapshot": plan,
        "billing_cycle_at_snapshot": cycle,
        "subscription_status_at_snapshot": status,
        "activated_before_snapshot": str(
            event_counts["task_completed"] > 0 or event_counts["workspace_created"] > 0
        ),
        "paid_before_snapshot": str(_plan_rank(plan) > 0),
    }


def _train_candidates(rows: list[FeatureRow], config: ChurnTrainingConfig) -> dict[str, Any]:
    y = np.array([row.label.behavioural_churn for row in rows])
    prevalence = float(y.mean()) if len(y) else 0.0
    candidates: dict[str, Any] = {"baseline": ConstantProbabilityModel(prevalence)}
    if len(set(y.tolist())) < 2:
        return candidates
    selected = {"logistic", "random_forest"} if config.model == "auto" else {config.model}
    if "logistic" in selected:
        candidates["logistic"] = _pipeline(
            LogisticRegression(
                class_weight="balanced",
                max_iter=1000,
                random_state=config.random_seed,
            )
        ).fit(_matrix(rows), y)
    if "random_forest" in selected:
        candidates["random_forest"] = _pipeline(
            RandomForestClassifier(
                n_estimators=100,
                min_samples_leaf=1,
                class_weight="balanced",
                random_state=config.random_seed,
            )
        ).fit(_matrix(rows), y)
    return candidates


def _pipeline(estimator: Any) -> Pipeline:
    return Pipeline(
        [
            (
                "preprocess",
                ColumnTransformer(
                    [
                        (
                            "numeric",
                            Pipeline(
                                [
                                    ("imputer", SimpleImputer(strategy="median")),
                                    ("scaler", StandardScaler()),
                                ]
                            ),
                            list(range(len(NUMERIC_FEATURES))),
                        ),
                        (
                            "categorical",
                            Pipeline(
                                [
                                    ("imputer", SimpleImputer(strategy="most_frequent")),
                                    ("onehot", OneHotEncoder(handle_unknown="ignore")),
                                ]
                            ),
                            list(
                                range(
                                    len(NUMERIC_FEATURES),
                                    len(NUMERIC_FEATURES) + len(CATEGORICAL_FEATURES),
                                )
                            ),
                        ),
                    ]
                ),
            ),
            ("model", estimator),
        ]
    )


def _select_model(
    candidates: dict[str, Any], validation_rows: list[FeatureRow], config: ChurnTrainingConfig
) -> dict[str, Any]:
    if config.model != "auto":
        return {"model_name": config.model, "model": candidates[config.model]}
    scored = []
    for name, model in candidates.items():
        probabilities = _probabilities(model, validation_rows)
        metrics = _evaluate(validation_rows, probabilities, 0.5)
        ap = _metric_value(metrics.get("average_precision"))
        brier = _metric_value(metrics.get("brier_score"), missing=1.0)
        scored.append((ap, -brier, 1 if name == "logistic" else 0, name, model))
    best = sorted(scored, reverse=True)[0]
    return {"model_name": best[3], "model": best[4]}


def _evaluate(
    rows: list[FeatureRow], probabilities: list[float], threshold: float
) -> dict[str, object]:
    y = [row.label.behavioural_churn for row in rows]
    predictions = [1 if probability >= threshold else 0 for probability in probabilities]
    if not rows:
        return {"row_count": 0}
    matrix = confusion_matrix(y, predictions, labels=[0, 1]).tolist()
    tn, fp = matrix[0]
    fn, tp = matrix[1]
    accuracy = _safe_div(tp + tn, len(y))
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    specificity = _safe_div(tn, tn + fp)
    f1 = _safe_div(2 * precision * recall, precision + recall)
    metrics: dict[str, object] = {
        "row_count": len(rows),
        "positive_count": sum(y),
        "prevalence": round(_safe_div(sum(y), len(y)), 6),
        "accuracy": accuracy,
        "balanced_accuracy": _safe_div(recall + specificity, 2) if len(set(y)) > 1 else None,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "confusion_matrix": {"labels": [0, 1], "matrix": matrix},
        "brier_score": round(float(brier_score_loss(y, probabilities)), 6),
        "top_decile_precision": _top_precision(y, probabilities, 0.1),
        "top_20_percent_recall": _top_recall(y, probabilities, 0.2),
        "calibration_bins": _calibration_bins(y, probabilities),
    }
    if len(set(y)) > 1:
        metrics["roc_auc"] = round(float(roc_auc_score(y, probabilities)), 6)
        metrics["average_precision"] = round(float(average_precision_score(y, probabilities)), 6)
        metrics["log_loss"] = round(float(log_loss(y, probabilities, labels=[0, 1])), 6)
    else:
        metrics["roc_auc"] = None
        metrics["average_precision"] = None
        metrics["log_loss"] = None
    return metrics


def _threshold_rows(rows: list[FeatureRow], probabilities: list[float]) -> list[Record]:
    output: list[Record] = []
    for threshold in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        metrics = _evaluate(rows, probabilities, threshold)
        output.append(
            {
                "threshold": threshold,
                "flagged_users": sum(
                    1 for probability in probabilities if probability >= threshold
                ),
                "precision": metrics.get("precision"),
                "recall": metrics.get("recall"),
                "f1": metrics.get("f1"),
                "balanced_accuracy": metrics.get("balanced_accuracy"),
            }
        )
    for capacity in (0.1, 0.2, 0.3):
        cutoff = _capacity_threshold(probabilities, capacity)
        metrics = _evaluate(rows, probabilities, cutoff)
        output.append(
            {
                "threshold": round(cutoff, 6),
                "flagged_users": sum(1 for probability in probabilities if probability >= cutoff),
                "precision": metrics.get("precision"),
                "recall": metrics.get("recall"),
                "f1": metrics.get("f1"),
                "balanced_accuracy": metrics.get("balanced_accuracy"),
                "capacity_rule": f"top_{int(capacity * 100)}_percent",
            }
        )
    return output


def _write_all(
    *,
    output_dir: Path,
    config: ChurnTrainingConfig,
    run_id: str,
    trusted_row_counts: dict[str, int],
    source_checksum: str,
    source_ingestion_run_id: str,
    contract_versions: dict[str, str],
    rows: list[FeatureRow],
    splits: list[Record],
    training_metrics: dict[str, object],
    validation_metrics: dict[str, object],
    test_metrics: dict[str, object],
    threshold_rows: list[Record],
    predictions: list[Record],
    feature_importance: list[Record],
    diagnostics: dict[str, object],
    selected_model: str,
    selected_threshold: float,
) -> dict[str, str]:
    files: dict[str, Callable[[Path], None]] = {
        "churn-definition.json": lambda path: _write_json(path, churn_definition(config)),
        "feature-catalogue.json": lambda path: _write_json(path, feature_catalogue()),
        "snapshot-labels.jsonl": lambda path: _write_jsonl(
            path, [row.label.to_record() for row in rows]
        ),
        "feature-matrix.csv": lambda path: _write_csv(path, [row.to_record() for row in rows]),
        "dataset-splits.csv": lambda path: _write_csv(path, splits),
        "training-metrics.json": lambda path: _write_json(path, training_metrics),
        "evaluation-metrics.json": lambda path: _write_json(
            path,
            {
                "validation": validation_metrics,
                "test": test_metrics,
                "subgroups": _subgroup_metrics(rows, splits, "persona", config.subgroup_threshold),
            },
        ),
        "threshold-analysis.csv": lambda path: _write_csv(path, threshold_rows),
        "predictions.csv": lambda path: _write_csv(path, predictions),
        "feature-importance.csv": lambda path: _write_csv(path, feature_importance),
        "model-metadata.json": lambda path: _write_json(
            path,
            _metadata(config, run_id, selected_model, selected_threshold),
        ),
        "model-card.md": lambda path: _write_text(
            path,
            _model_card(
                config, selected_model, selected_threshold, validation_metrics, test_metrics
            ),
        ),
        "run-diagnostics.json": lambda path: _write_json(path, diagnostics),
        "model-lineage.json": lambda path: _write_json(
            path,
            {
                "source_ingestion_run_id": source_ingestion_run_id,
                "source_manifest_checksum": source_checksum,
                "source_contract_versions": contract_versions,
                "relationships": [
                    "trusted accepted datasets",
                    "point-in-time snapshot generation",
                    "future behavioural churn labels",
                    "training-only preprocessing",
                    "chronological validation selection",
                    "held-out test evaluation",
                ],
            },
        ),
    }
    checksums: dict[str, str] = {}
    for filename, writer in files.items():
        path = output_dir / filename
        writer(path)
        checksums[filename] = file_sha256(path)
    manifest = {
        "model_run_id": run_id,
        "model_version": CHURN_VERSION,
        "source_ingestion_run_id": source_ingestion_run_id,
        "source_manifest_checksum": source_checksum,
        "input_row_counts": trusted_row_counts,
        "output_row_counts": {
            "snapshot-labels.jsonl": len(rows),
            "feature-matrix.csv": len(rows),
            "dataset-splits.csv": len(splits),
            "predictions.csv": len(predictions),
        },
        "output_checksums": checksums,
        "selected_model": selected_model,
        "selected_threshold": selected_threshold,
        "overall_status": diagnostics["overall_status"],
        "created_at": config.fixed_run_time,
    }
    _write_json(output_dir / "model-manifest.json", manifest)
    checksums["model-manifest.json"] = file_sha256(output_dir / "model-manifest.json")
    return checksums


def churn_definition(config: ChurnTrainingConfig) -> Record:
    """Return the governed churn definition."""

    return {
        "definition_id": "behavioural_churn",
        "version": CHURN_VERSION,
        "analytical_entity": "user",
        "snapshot_cadence": config.snapshot_cadence,
        "lookback_days": config.lookback_days,
        "label_window_days": config.label_window_days,
        "primary_label": "no qualifying product activity after snapshot through label window end",
        "qualifying_events": list(DEFAULT_QUALIFYING_EVENTS),
        "supporting_outcomes": [
            "subscription_cancelled",
            "subscription_downgraded",
            "paid_inactive",
            "free_inactive",
        ],
        "leakage_policy": (
            "features use records at or before snapshot only; labels use records "
            "strictly after snapshot"
        ),
    }


def feature_catalogue() -> list[Record]:
    """Return feature metadata."""

    rows = []
    for name in NUMERIC_FEATURES:
        rows.append({"feature_name": name, "type": "numeric", "window": "point_in_time_lookback"})
    for name in CATEGORICAL_FEATURES:
        rows.append({"feature_name": name, "type": "categorical", "window": "point_in_time"})
    return rows


def _chronological_splits(
    rows: list[FeatureRow], lookback_days: int, label_window_days: int
) -> list[Record]:
    ordered = sorted(rows, key=lambda row: (row.label.snapshot_timestamp, row.label.user_id))
    n = len(ordered)
    train_end = max(1, math.floor(n * 0.6))
    validation_end = max(train_end + 1, math.floor(n * 0.8))
    if validation_end >= n:
        validation_end = n - 1
    splits = []
    for index, row in enumerate(ordered):
        split = "train" if index < train_end else "validation" if index < validation_end else "test"
        splits.append(
            {
                "snapshot_id": row.label.snapshot_id,
                "user_id": row.label.user_id,
                "snapshot_timestamp": row.label.snapshot_timestamp,
                "split": split,
                "lookback_days": lookback_days,
                "label_window_days": label_window_days,
                "purge_gap_days": 0,
                "behavioural_churn": row.label.behavioural_churn,
            }
        )
    return splits


def _diagnostics(
    rows: list[FeatureRow],
    splits: list[Record],
    config: ChurnTrainingConfig,
    validation_metrics: dict[str, object],
    test_metrics: dict[str, object],
) -> dict[str, object]:
    split_counts = Counter(str(row["split"]) for row in splits)
    return {
        "overall_status": "passed",
        "snapshot_count": len(rows),
        "label_prevalence": round(sum(row.label.behavioural_churn for row in rows) / len(rows), 6),
        "split_counts": dict(sorted(split_counts.items())),
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "leakage_checks": {
            "post_snapshot_features_excluded": True,
            "future_subscription_changes_excluded": True,
            "label_window_activity_excluded_from_features": True,
            "preprocessing_fitted_on_training_only": True,
        },
        "configuration": {
            "lookback_days": config.lookback_days,
            "label_window_days": config.label_window_days,
            "snapshot_cadence": config.snapshot_cadence,
        },
    }


def _metadata(
    config: ChurnTrainingConfig, run_id: str, selected_model: str, selected_threshold: float
) -> Record:
    return {
        "model_run_id": run_id,
        "model_version": CHURN_VERSION,
        "software_version": get_project_metadata().version,
        "selected_model": selected_model,
        "selected_threshold": selected_threshold,
        "selection_metric": (
            "validation average precision then Brier score; logistic preferred on ties"
        ),
        "random_seed": config.random_seed,
        "created_at": config.fixed_run_time,
        "training_scope": "synthetic trusted Milestone 3 accepted NexaFlow datasets",
    }


def _model_card(
    config: ChurnTrainingConfig,
    selected_model: str,
    selected_threshold: float,
    validation_metrics: dict[str, object],
    test_metrics: dict[str, object],
) -> str:
    return "\n".join(
        [
            "# Churn Prediction Model Card",
            "",
            "This model is a deterministic demonstration over synthetic NexaFlow data.",
            "",
            f"- Primary target: behavioural churn over {config.label_window_days} days.",
            (
                f"- Snapshot design: {config.lookback_days}-day point-in-time lookback, "
                "then future label window."
            ),
            f"- Selected model: {selected_model}.",
            f"- Selected threshold: {selected_threshold}.",
            f"- Validation F1: {validation_metrics.get('f1')}.",
            f"- Test F1: {test_metrics.get('f1')}.",
            "",
            "Predictions are probabilistic and feature importance is associative, not causal.",
            "This model must not be used for automated adverse decisions.",
            "",
            "Recommended next investigations: validate on larger samples, review",
            "fairness-sensitive",
            "subgroups, monitor drift, and compare interventions through governed experiments.",
            "",
        ]
    )


def _subgroup_metrics(
    rows: list[FeatureRow], splits: list[Record], feature_name: str, threshold: int
) -> list[Record]:
    by_split = {str(row["snapshot_id"]): str(row["split"]) for row in splits}
    groups: dict[str, list[FeatureRow]] = defaultdict(list)
    for row in rows:
        if by_split[row.label.snapshot_id] == "test":
            groups[str(row.features.get(feature_name, "unknown"))].append(row)
    return [
        {
            "feature": feature_name,
            "value": value,
            "row_count": len(group_rows),
            "positive_count": sum(row.label.behavioural_churn for row in group_rows),
            "prevalence": round(
                _safe_div(sum(row.label.behavioural_churn for row in group_rows), len(group_rows)),
                6,
            ),
            "suppression_status": "shown" if len(group_rows) >= threshold else "suppressed",
        }
        for value, group_rows in sorted(groups.items())
    ]


def _feature_importance(model: Any, model_name: str) -> list[Record]:
    if model_name == "baseline":
        return [{"feature_name": "baseline_prevalence", "importance": 1.0, "direction": "constant"}]
    preprocessor = model.named_steps["preprocess"]
    names = _transformed_feature_names(preprocessor)
    estimator = model.named_steps["model"]
    if model_name == "logistic":
        values = estimator.coef_[0]
        rows = [
            {
                "feature_name": name,
                "importance": round(float(abs(value)), 6),
                "signed_value": round(float(value), 6),
            }
            for name, value in zip(names, values, strict=True)
        ]
    else:
        rows = [
            {"feature_name": name, "importance": round(float(value), 6), "signed_value": None}
            for name, value in zip(names, estimator.feature_importances_, strict=True)
        ]
    return sorted(
        rows, key=lambda row: (float(row["importance"]), str(row["feature_name"])), reverse=True
    )


def _transformed_feature_names(preprocessor: Any) -> list[str]:
    categorical_pipeline = preprocessor.named_transformers_["categorical"]
    onehot = categorical_pipeline.named_steps["onehot"]
    categorical_names: list[str] = []
    for feature_name, categories in zip(CATEGORICAL_FEATURES, onehot.categories_, strict=True):
        categorical_names.extend(f"{feature_name}={category}" for category in categories)
    return [*NUMERIC_FEATURES, *categorical_names]


def _prediction_rows(
    rows: list[FeatureRow], probabilities: list[float], threshold: float
) -> list[Record]:
    return [
        {
            "snapshot_id": row.label.snapshot_id,
            "user_id": row.label.user_id,
            "snapshot_timestamp": row.label.snapshot_timestamp,
            "actual_behavioural_churn": row.label.behavioural_churn,
            "churn_probability": round(probability, 6),
            "predicted_behavioural_churn": 1 if probability >= threshold else 0,
            "risk_band": _risk_band(probability),
        }
        for row, probability in zip(rows, probabilities, strict=True)
    ]


def _probabilities(model: Any, rows: list[FeatureRow]) -> list[float]:
    if not rows:
        return []
    return [float(value) for value in model.predict_proba(_matrix(rows))[:, 1]]


def _matrix(rows: list[FeatureRow]) -> list[list[object]]:
    return [[row.features.get(feature) for feature in FEATURE_COLUMNS] for row in rows]


def _select_threshold(
    rows: list[Record], probabilities: list[float], config: ChurnTrainingConfig
) -> float:
    if config.selected_threshold_rule == "fixed_0_5":
        return 0.5
    if config.selected_threshold_rule == "top_20_percent":
        return _capacity_threshold(probabilities, 0.2)
    best = max(rows[:7], key=lambda row: (float(row.get("f1") or 0), float(row["threshold"])))
    return float(best["threshold"])


def _capacity_threshold(probabilities: list[float], capacity: float) -> float:
    if not probabilities:
        return 1.0
    ordered = sorted(probabilities, reverse=True)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * capacity) - 1))
    return float(ordered[index])


def _calibration_bins(y: list[int], probabilities: list[float]) -> list[Record]:
    bins: list[Record] = []
    for lower in (0.0, 0.25, 0.5, 0.75):
        upper = lower + 0.25
        pairs = [
            (actual, probability)
            for actual, probability in zip(y, probabilities, strict=True)
            if lower <= probability < upper or (upper == 1.0 and probability == 1.0)
        ]
        bins.append(
            {
                "lower": lower,
                "upper": upper,
                "row_count": len(pairs),
                "average_probability": round(_safe_div(sum(p for _, p in pairs), len(pairs)), 6),
                "observed_rate": round(_safe_div(sum(a for a, _ in pairs), len(pairs)), 6),
            }
        )
    return bins


def _top_precision(y: list[int], probabilities: list[float], capacity: float) -> float:
    pairs = sorted(zip(probabilities, y, strict=True), reverse=True)
    top = pairs[: max(1, math.ceil(len(pairs) * capacity))]
    return round(_safe_div(sum(actual for _, actual in top), len(top)), 6)


def _top_recall(y: list[int], probabilities: list[float], capacity: float) -> float:
    pairs = sorted(zip(probabilities, y, strict=True), reverse=True)
    top = pairs[: max(1, math.ceil(len(pairs) * capacity))]
    return round(_safe_div(sum(actual for _, actual in top), sum(y)), 6)


def _records_by_user(records: list[Record]) -> defaultdict[str, list[Record]]:
    by_user: defaultdict[str, list[Record]] = defaultdict(list)
    for record in records:
        by_user[str(record["user_id"])].append(record)
    return by_user


def _subscription_context(
    subscriptions: list[Record], snapshot: datetime
) -> tuple[str, str, str, float, int]:
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
        return ("unknown", "unknown", "unknown", 0.0, 0)
    selected = sorted(active, key=lambda sub: str(sub["period_start_timestamp"]))[-1]
    start = _parse_dt(str(selected["period_start_timestamp"]))
    return (
        str(selected.get("plan_name", "unknown")),
        str(selected.get("billing_cycle", "unknown")),
        str(selected.get("status", "unknown")),
        float(selected.get("monthly_recurring_revenue", 0) or 0),
        (snapshot - start).days,
    )


def _plan_at_snapshot(subscriptions: list[Record], snapshot: datetime) -> str:
    return _subscription_context(subscriptions, snapshot)[0]


def _plan_rank(plan: str) -> int:
    return {"free": 0, "starter": 1, "pro": 2, "business": 3, "enterprise": 4}.get(plan, 0)


def _count_feature(events: list[Record], usage: list[Record], feature: str) -> int:
    return sum(
        1 for event in events if str(event.get("feature_name", "")).startswith(feature)
    ) + sum(
        int(row.get("usage_count", 0) or 0)
        for row in usage
        if str(row.get("feature_name", "")).startswith(feature)
    )


def _longest_gap(days: list[date]) -> int:
    if len(days) < 2:
        return 0
    return int(max((b - a).days for a, b in zip(days, days[1:], strict=False)))


def _safe_div(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _risk_band(probability: float) -> str:
    if probability >= 0.7:
        return "high"
    if probability >= 0.4:
        return "medium"
    return "low"


def _metric_value(value: object, missing: float = 0.0) -> float:
    if isinstance(value, int | float):
        return float(value)
    return missing


def _default_run_id(config: ChurnTrainingConfig) -> str:
    if config.fixed_run_time:
        stamp = (
            config.fixed_run_time.replace(":", "")
            .replace("-", "")
            .replace("T", "-")
            .replace("Z", "")
        )
    else:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"churn-{stamp}"


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


def run_sample_to_temp() -> ChurnTrainingResult:
    """Run sample ingestion then churn training in a temporary directory."""

    from product_growth_intelligence.ingestion import IngestionConfig, run_batch_ingestion

    with TemporaryDirectory() as temp:
        root = Path(temp)
        ingestion = run_batch_ingestion(
            IngestionConfig(
                source=Path("data/samples/nexaflow"),
                output_root=root / "interim",
                quality_root=root / "quality",
                run_id="milestone6-source",
                fixed_ingestion_time="2026-01-01T00:00:00Z",
                overwrite=True,
            )
        )
        return run_churn_training(
            ChurnTrainingConfig(
                input_dir=ingestion.output_dir,
                output_root=root / "churn",
                run_id="milestone6-churn",
                analysis_end="2025-03-31T23:59:59Z",
                fixed_run_time="2026-01-02T00:00:00Z",
                overwrite=True,
            )
        )


JsonReady = dict[str, JsonValue]
