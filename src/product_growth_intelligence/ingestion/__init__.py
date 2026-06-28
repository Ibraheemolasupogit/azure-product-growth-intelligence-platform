"""Local ingestion and data-quality pipeline."""

from product_growth_intelligence.ingestion.batch import run_batch_ingestion
from product_growth_intelligence.ingestion.models import IngestionConfig, PipelineResult
from product_growth_intelligence.ingestion.streaming import run_stream_ingestion

__all__ = ["IngestionConfig", "PipelineResult", "run_batch_ingestion", "run_stream_ingestion"]
