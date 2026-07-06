"""Typed models for governed experiment analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

CorrectionMethod = Literal["none", "bonferroni", "benjamini_hochberg"]
MetricType = Literal["binary", "continuous", "count"]
Population = Literal["intention_to_treat", "exposed"]
Decision = Literal[
    "ship",
    "ship_with_caution",
    "continue_experiment",
    "no_clear_evidence",
    "do_not_ship",
    "invalid_experiment",
]


@dataclass(frozen=True)
class MetricSpec:
    """Governed experiment metric definition."""

    metric_id: str
    name: str
    metric_type: MetricType
    business_meaning: str
    event_names: tuple[str, ...] = ()
    direction: Literal["increase", "decrease"] = "increase"
    practical_threshold: float = 0.0
    attribution_basis: str = "assignment_or_exposure"
    unit: str = "proportion"
    null_handling: str = "zero when denominator is zero"
    guardrail: bool = False
    critical: bool = False
    harm_threshold: float = 0.0


@dataclass(frozen=True)
class ExperimentSpec:
    """Versioned experiment-analysis specification."""

    experiment_id: str
    experiment_name: str
    version: str
    business_hypothesis: str
    randomisation_unit: str
    eligibility_population: str
    variants: tuple[str, ...]
    control_variant: str
    treatment_variants: tuple[str, ...]
    planned_allocation: dict[str, float]
    assignment_start: str
    assignment_end: str
    exposure_event: str
    primary_metric: str
    secondary_metrics: tuple[str, ...]
    guardrail_metrics: tuple[str, ...]
    analysis_window_days: int
    attribution_window_days: int
    minimum_sample_size: int
    minimum_detectable_effect: float
    significance_level: float
    target_power: float
    sidedness: Literal["two_sided"] = "two_sided"
    multiple_testing_family: str = "experiment_metric_family"
    segment_dimensions: tuple[str, ...] = ()
    exclusion_rules: tuple[str, ...] = ()
    decision_rule: str = "governed_primary_metric_with_guardrails"
    owner: str = "Growth analytics"
    status: str = "active"


@dataclass(frozen=True)
class ExperimentAnalysisConfig:
    """Configuration for one governed experiment-analysis run."""

    input_dir: Path
    output_root: Path
    run_id: str | None = None
    experiment_ids: tuple[str, ...] = ()
    analysis_time: str = "2025-06-30T23:59:59Z"
    populations: tuple[Population, ...] = ("intention_to_treat", "exposed")
    significance_level: float = 0.05
    confidence_level: float = 0.95
    multiple_testing: CorrectionMethod = "benjamini_hochberg"
    srm_p_value_threshold: float = 0.01
    minimum_sample_size: int = 2
    segment_dimensions: tuple[str, ...] = (
        "persona",
        "acquisition_channel",
        "initial_plan",
        "company_size_band",
        "is_team_account",
        "region",
    )
    suppression_threshold: int = 2
    fixed_run_time: str | None = None
    overwrite: bool = False
    validate_only: bool = False
    evidence_mode: bool = False

    def validate(self) -> None:
        """Validate configuration values."""

        if not 0 < self.significance_level < 1:
            msg = "significance_level must be between zero and one."
            raise ValueError(msg)
        if not 0 < self.confidence_level < 1:
            msg = "confidence_level must be between zero and one."
            raise ValueError(msg)
        if self.multiple_testing not in {"none", "bonferroni", "benjamini_hochberg"}:
            msg = "Unsupported multiple-testing method."
            raise ValueError(msg)
        if not 0 < self.srm_p_value_threshold < 1:
            msg = "srm_p_value_threshold must be between zero and one."
            raise ValueError(msg)
        if self.minimum_sample_size < 0:
            msg = "minimum_sample_size cannot be negative."
            raise ValueError(msg)
        if self.suppression_threshold < 0:
            msg = "suppression_threshold cannot be negative."
            raise ValueError(msg)
        if any(
            population not in {"intention_to_treat", "exposed"} for population in self.populations
        ):
            msg = "Unsupported analysis population."
            raise ValueError(msg)


@dataclass(frozen=True)
class ExperimentAnalysisResult:
    """Completed experiment-analysis run summary."""

    run_id: str
    status: str
    output_dir: Path
    experiments_evaluated: int
    decisions: dict[str, Decision]
    diagnostics: dict[str, object] = field(default_factory=dict)
