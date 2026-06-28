"""Synthetic NexaFlow product data generation."""

from product_growth_intelligence.data_generation.generator import generate_datasets
from product_growth_intelligence.data_generation.models import GeneratedDatasets, GenerationConfig
from product_growth_intelligence.data_generation.profiles import default_generation_config
from product_growth_intelligence.data_generation.writers import write_datasets

__all__ = [
    "GeneratedDatasets",
    "GenerationConfig",
    "default_generation_config",
    "generate_datasets",
    "write_datasets",
]
