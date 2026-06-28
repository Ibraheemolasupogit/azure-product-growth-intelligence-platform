import pytest

from product_growth_intelligence.randomness import (
    DEFAULT_RANDOM_SEED,
    normalize_seed,
    seeded_random,
)


def test_normalize_seed_defaults_to_project_seed():
    assert normalize_seed() == DEFAULT_RANDOM_SEED


def test_normalize_seed_accepts_numeric_strings():
    assert normalize_seed("123") == 123


def test_normalize_seed_rejects_negative_values():
    with pytest.raises(ValueError, match="non-negative"):
        normalize_seed(-1)


def test_seeded_random_is_deterministic():
    first = seeded_random(7).random()
    second = seeded_random(7).random()
    assert first == second
