"""Governed recommendation baseline workflow."""

from product_growth_intelligence.models.recommendations.models import (
    RecommendationConfig,
    RecommendationResult,
)
from product_growth_intelligence.models.recommendations.pipeline import run_recommendations

__all__ = ["RecommendationConfig", "RecommendationResult", "run_recommendations"]
