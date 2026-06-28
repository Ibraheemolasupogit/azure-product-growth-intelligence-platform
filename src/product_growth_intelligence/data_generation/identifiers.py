"""Stable synthetic identifier helpers."""

from uuid import UUID, uuid5

SYNTHETIC_NAMESPACE = UUID("70ad5116-49ac-47a8-916a-fc0dc1ddfc73")


def stable_id(prefix: str, *parts: object) -> str:
    """Return a deterministic synthetic identifier for persisted records."""

    key = "|".join(str(part) for part in parts)
    return f"syn_{prefix}_{uuid5(SYNTHETIC_NAMESPACE, f'{prefix}|{key}').hex[:16]}"
