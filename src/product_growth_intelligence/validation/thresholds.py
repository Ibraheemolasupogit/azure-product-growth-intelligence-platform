"""Quality threshold helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThresholdConfig:
    """Failure-threshold configuration."""

    max_quarantine_rate: float = 0.0
    max_critical_failures: int = 0
    checksum_mismatch_is_fatal: bool = True

    def validate(self) -> None:
        """Validate threshold values."""

        if not 0 <= self.max_quarantine_rate <= 1:
            msg = "max_quarantine_rate must be between 0 and 1."
            raise ValueError(msg)
        if self.max_critical_failures < 0:
            msg = "max_critical_failures cannot be negative."
            raise ValueError(msg)
