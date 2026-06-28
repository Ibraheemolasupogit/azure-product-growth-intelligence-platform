"""Stable cryptographic record fingerprints."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from os import PathLike
from pathlib import Path

from product_growth_intelligence.data_generation.models import JsonValue, Record


def record_fingerprint(record: Record) -> str:
    """Return a deterministic SHA-256 fingerprint for a business record."""

    canonical = json.dumps(
        _normalise(record),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalise(value: object) -> JsonValue:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [_normalise(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalise(item) for key, item in value.items()}
    return str(value)


def file_sha256(path: str | PathLike[str]) -> str:
    """Return a SHA-256 checksum for a file path."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
