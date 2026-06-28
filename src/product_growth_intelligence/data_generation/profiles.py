"""Synthetic data generation profiles and configuration validation."""

from datetime import date
from pathlib import Path

from product_growth_intelligence.data_generation.catalogues import (
    ACQUISITION_CHANNELS,
    COUNTRIES,
    PERSONAS,
)
from product_growth_intelligence.data_generation.models import GenerationConfig

SUPPORTED_PROFILES = frozenset({"sample", "development"})


def default_generation_config(profile: str, output_dir: Path | None = None) -> GenerationConfig:
    """Build a default generation config for a supported profile."""

    normalized = profile.lower().strip()
    if normalized not in SUPPORTED_PROFILES:
        allowed = ", ".join(sorted(SUPPORTED_PROFILES))
        msg = f"Unsupported generation profile '{profile}'. Expected one of: {allowed}."
        raise ValueError(msg)

    user_count = 12 if normalized == "sample" else 250
    default_output = Path("data") / "raw" / f"{normalized}-run"
    return GenerationConfig(
        profile=normalized,
        user_count=user_count,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 3, 31),
        seed=42,
        output_dir=output_dir or default_output,
        timezone="UTC",
        persona_distribution={
            "solo_professional": 0.22,
            "small_team_member": 0.20,
            "team_admin": 0.16,
            "operations_lead": 0.14,
            "casual_explorer": 0.16,
            "power_user": 0.12,
        },
        acquisition_channel_distribution={
            "organic_search": 0.24,
            "paid_search": 0.16,
            "content_marketing": 0.18,
            "partner_referral": 0.14,
            "product_led_referral": 0.18,
            "app_marketplace": 0.10,
        },
        country_distribution={
            "United States": 0.34,
            "United Kingdom": 0.20,
            "Canada": 0.14,
            "Australia": 0.12,
            "Germany": 0.11,
            "Netherlands": 0.09,
        },
        feedback_probability=0.24 if normalized == "sample" else 0.16,
    )


def validate_generation_config(config: GenerationConfig) -> None:
    """Validate generation settings before data is produced."""

    if config.profile not in SUPPORTED_PROFILES:
        msg = f"Unsupported generation profile '{config.profile}'."
        raise ValueError(msg)
    if config.user_count <= 0:
        msg = "Synthetic user count must be greater than zero."
        raise ValueError(msg)
    if config.end_date < config.start_date:
        msg = "Simulation end date must be on or after the start date."
        raise ValueError(msg)
    if config.timezone != "UTC":
        msg = "Only UTC timestamps are supported for deterministic generation."
        raise ValueError(msg)
    _validate_distribution("persona", config.persona_distribution, PERSONAS)
    _validate_distribution(
        "acquisition channel", config.acquisition_channel_distribution, ACQUISITION_CHANNELS
    )
    _validate_distribution("country", config.country_distribution, COUNTRIES)
    if not 0 <= config.feedback_probability <= 1:
        msg = "Feedback probability must be between 0 and 1."
        raise ValueError(msg)
    _validate_output_path(config.output_dir)


def _validate_distribution(
    name: str, distribution: dict[str, float], allowed_values: tuple[str, ...]
) -> None:
    if not distribution:
        msg = f"{name.title()} distribution cannot be empty."
        raise ValueError(msg)
    unknown_values = sorted(set(distribution) - set(allowed_values))
    if unknown_values:
        msg = f"Unknown {name} values: {', '.join(unknown_values)}."
        raise ValueError(msg)
    total = sum(distribution.values())
    if any(value < 0 for value in distribution.values()) or abs(total - 1.0) > 0.000001:
        msg = f"{name.title()} distribution probabilities must be non-negative and sum to 1."
        raise ValueError(msg)


def _validate_output_path(output_dir: Path) -> None:
    if not output_dir.parts:
        msg = "Output directory cannot be empty."
        raise ValueError(msg)
    if output_dir.is_absolute():
        return
    allowed_prefixes = ((Path("data") / "raw").parts, (Path("data") / "samples").parts)
    if not any(output_dir.parts[: len(prefix)] == prefix for prefix in allowed_prefixes):
        msg = "Relative output directories must be under data/raw or data/samples."
        raise ValueError(msg)
