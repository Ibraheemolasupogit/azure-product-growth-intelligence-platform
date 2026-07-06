"""Deterministic statistical helpers for experiment analysis."""

from __future__ import annotations

import math
from collections.abc import Iterable

from scipy import stats  # type: ignore[import-untyped]

from product_growth_intelligence.experiments.models import CorrectionMethod


def two_proportion_effect(
    control_successes: int,
    control_n: int,
    treatment_successes: int,
    treatment_n: int,
    confidence_level: float,
) -> dict[str, float | str]:
    """Calculate a two-proportion z-test and absolute-effect CI."""

    control_rate = _safe_div(control_successes, control_n)
    treatment_rate = _safe_div(treatment_successes, treatment_n)
    effect = treatment_rate - control_rate
    pooled = _safe_div(control_successes + treatment_successes, control_n + treatment_n)
    pooled_se = math.sqrt(
        pooled * (1 - pooled) * _safe_div(control_n + treatment_n, control_n * treatment_n)
    )
    unpooled_se = math.sqrt(
        _safe_div(control_rate * (1 - control_rate), control_n)
        + _safe_div(treatment_rate * (1 - treatment_rate), treatment_n)
    )
    z_score = _safe_div(effect, pooled_se)
    alpha = 1 - confidence_level
    critical = float(stats.norm.ppf(1 - alpha / 2))
    return {
        "control_value": round(control_rate, 6),
        "treatment_value": round(treatment_rate, 6),
        "absolute_effect": round(effect, 6),
        "relative_effect": round(_safe_div(effect, control_rate), 6),
        "risk_ratio": round(_safe_div(treatment_rate, control_rate), 6),
        "odds_ratio": round(
            _odds_ratio(control_successes, control_n, treatment_successes, treatment_n), 6
        ),
        "confidence_lower": round(effect - critical * unpooled_se, 6),
        "confidence_upper": round(effect + critical * unpooled_se, 6),
        "standard_error": round(pooled_se, 6),
        "test_statistic": round(z_score, 6),
        "p_value": round(2 * (1 - float(stats.norm.cdf(abs(z_score)))), 6),
        "confidence_method": "normal_approximation_unpooled_absolute_difference",
        "test_method": "two_proportion_z_test",
    }


def welch_mean_effect(
    control_values: list[float],
    treatment_values: list[float],
    confidence_level: float,
) -> dict[str, float | str]:
    """Calculate Welch's t-test and mean-difference CI."""

    control_n = len(control_values)
    treatment_n = len(treatment_values)
    control_mean = _mean(control_values)
    treatment_mean = _mean(treatment_values)
    effect = treatment_mean - control_mean
    control_var = _sample_variance(control_values)
    treatment_var = _sample_variance(treatment_values)
    se = math.sqrt(_safe_div(control_var, control_n) + _safe_div(treatment_var, treatment_n))
    df = _welch_df(control_var, control_n, treatment_var, treatment_n)
    t_statistic = _safe_div(effect, se)
    alpha = 1 - confidence_level
    critical = float(stats.t.ppf(1 - alpha / 2, df)) if df > 0 else 0.0
    p_value = 2 * (1 - float(stats.t.cdf(abs(t_statistic), df))) if df > 0 else 1.0
    return {
        "control_value": round(control_mean, 6),
        "treatment_value": round(treatment_mean, 6),
        "absolute_effect": round(effect, 6),
        "relative_effect": round(_safe_div(effect, control_mean), 6),
        "risk_ratio": 0.0,
        "odds_ratio": 0.0,
        "confidence_lower": round(effect - critical * se, 6),
        "confidence_upper": round(effect + critical * se, 6),
        "standard_error": round(se, 6),
        "test_statistic": round(t_statistic, 6),
        "p_value": round(p_value, 6),
        "confidence_method": "welch_t_interval_mean_difference",
        "test_method": "welch_t_test",
    }


def chi_square_srm(observed: list[int], expected_shares: list[float]) -> dict[str, float | str]:
    """Calculate a chi-square sample-ratio mismatch test."""

    total = sum(observed)
    expected = [total * share for share in expected_shares]
    if not observed or total == 0 or any(value <= 0 for value in expected):
        return {
            "test_statistic": 0.0,
            "degrees_of_freedom": max(len(observed) - 1, 0),
            "p_value": 1.0,
            "method": "chi_square_goodness_of_fit_unavailable",
        }
    statistic, p_value = stats.chisquare(observed, expected)
    return {
        "test_statistic": round(float(statistic), 6),
        "degrees_of_freedom": len(observed) - 1,
        "p_value": round(float(p_value), 6),
        "method": "chi_square_goodness_of_fit",
    }


def adjust_p_values(p_values: Iterable[float], method: CorrectionMethod) -> list[float]:
    """Apply deterministic p-value correction."""

    values = [min(max(float(value), 0.0), 1.0) for value in p_values]
    if method == "none" or not values:
        return [round(value, 6) for value in values]
    if method == "bonferroni":
        return [round(min(value * len(values), 1.0), 6) for value in values]
    indexed = sorted(enumerate(values), key=lambda item: item[1], reverse=True)
    adjusted = [1.0] * len(values)
    running = 1.0
    total = len(values)
    for rank_from_largest, (index, value) in enumerate(indexed, start=1):
        rank = total - rank_from_largest + 1
        running = min(running, value * total / rank)
        adjusted[index] = min(running, 1.0)
    return [round(value, 6) for value in adjusted]


def binary_required_sample_size(
    baseline_rate: float,
    minimum_detectable_effect: float,
    significance_level: float,
    target_power: float,
) -> int:
    """Approximate required sample size per variant for a binary metric."""

    if minimum_detectable_effect <= 0:
        return 0
    baseline = min(max(baseline_rate, 0.001), 0.999)
    treatment = min(max(baseline + minimum_detectable_effect, 0.001), 0.999)
    pooled = (baseline + treatment) / 2
    z_alpha = float(stats.norm.ppf(1 - significance_level / 2))
    z_power = float(stats.norm.ppf(target_power))
    variance = 2 * pooled * (1 - pooled)
    return max(math.ceil(((z_alpha + z_power) ** 2 * variance) / minimum_detectable_effect**2), 1)


def _odds_ratio(
    control_successes: int, control_n: int, treatment_successes: int, treatment_n: int
) -> float:
    control_failures = control_n - control_successes
    treatment_failures = treatment_n - treatment_successes
    return ((treatment_successes + 0.5) * (control_failures + 0.5)) / (
        (treatment_failures + 0.5) * (control_successes + 0.5)
    )


def _welch_df(control_var: float, control_n: int, treatment_var: float, treatment_n: int) -> float:
    left = _safe_div(control_var, control_n)
    right = _safe_div(treatment_var, treatment_n)
    numerator = (left + right) ** 2
    denominator = _safe_div(left**2, control_n - 1) + _safe_div(right**2, treatment_n - 1)
    return _safe_div(numerator, denominator)


def _sample_variance(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    mean = _mean(values)
    return sum((value - mean) ** 2 for value in values) / (len(values) - 1)


def _mean(values: list[float]) -> float:
    return _safe_div(sum(values), len(values))


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0
