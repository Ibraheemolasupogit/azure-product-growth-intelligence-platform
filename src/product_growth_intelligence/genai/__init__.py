"""Deterministic product insight assistant."""

from product_growth_intelligence.genai.models import ProductInsightConfig, ProductInsightResult
from product_growth_intelligence.genai.pipeline import (
    build_insight_inputs,
    generate_grounded_insights,
    load_evidence,
    run_governance_checks,
    run_product_insights,
)

__all__ = [
    "ProductInsightConfig",
    "ProductInsightResult",
    "build_insight_inputs",
    "generate_grounded_insights",
    "load_evidence",
    "run_governance_checks",
    "run_product_insights",
]
