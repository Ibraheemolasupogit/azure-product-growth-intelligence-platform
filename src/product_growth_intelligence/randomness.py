"""Deterministic seed helpers."""

import random

DEFAULT_RANDOM_SEED = 42


def normalize_seed(seed: int | str | None = None) -> int:
    """Convert a configured seed value to a deterministic integer."""

    if seed is None:
        return DEFAULT_RANDOM_SEED
    if isinstance(seed, int):
        if seed < 0:
            msg = "Random seed must be non-negative."
            raise ValueError(msg)
        return seed
    parsed = int(seed)
    if parsed < 0:
        msg = "Random seed must be non-negative."
        raise ValueError(msg)
    return parsed


def seeded_random(seed: int | str | None = None) -> random.Random:
    """Create an isolated deterministic random number generator."""

    return random.Random(normalize_seed(seed))
