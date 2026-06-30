"""UTC period indexing for retention analytics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from product_growth_intelligence.analytics.retention.models import TimeGrain


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO timestamp as UTC-aware datetime."""

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC)


def period_start(timestamp: datetime, grain: TimeGrain) -> datetime:
    """Return deterministic period start."""

    value = timestamp.astimezone(UTC)
    if grain == "daily":
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if grain == "weekly":
        start = datetime(value.year, value.month, value.day, tzinfo=UTC)
        return start - timedelta(days=start.weekday())
    return datetime(value.year, value.month, 1, tzinfo=UTC)


def add_periods(start: datetime, periods: int, grain: TimeGrain) -> datetime:
    """Add daily, ISO-weekly or calendar-month periods."""

    if grain == "daily":
        return start + timedelta(days=periods)
    if grain == "weekly":
        return start + timedelta(weeks=periods)
    month_index = start.month - 1 + periods
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    return datetime(year, month, 1, tzinfo=UTC)


def period_index(anchor: datetime, timestamp: datetime, grain: TimeGrain) -> int:
    """Return zero-based period index relative to anchor period."""

    anchor_period = period_start(anchor, grain)
    timestamp_period = period_start(timestamp, grain)
    if grain == "daily":
        return (timestamp_period - anchor_period).days
    if grain == "weekly":
        return (timestamp_period - anchor_period).days // 7
    return (timestamp_period.year - anchor_period.year) * 12 + (
        timestamp_period.month - anchor_period.month
    )


def iso(value: datetime) -> str:
    """Return stable UTC timestamp text."""

    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def period_label(value: datetime, grain: TimeGrain) -> str:
    """Return stable period label."""

    start = period_start(value, grain)
    if grain == "daily":
        return start.date().isoformat()
    if grain == "weekly":
        year, week, _ = start.isocalendar()
        return f"{year}-W{week:02d}"
    return f"{start.year}-{start.month:02d}"
