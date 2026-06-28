"""Typed quality-rule result models for ingestion validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from product_growth_intelligence.data_generation.models import JsonValue

Severity = Literal["info", "warning", "error", "critical"]
RuleCategory = Literal[
    "file_integrity",
    "schema",
    "completeness",
    "validity",
    "uniqueness",
    "temporal_integrity",
    "referential_integrity",
    "consistency",
    "freshness",
    "schema_drift",
]


@dataclass(frozen=True)
class SourceLocation:
    """Location of a source record or file-level finding."""

    file_name: str
    row_number: int | None = None
    line_number: int | None = None

    def to_dict(self) -> dict[str, JsonValue]:
        """Return a JSON-serialisable representation."""

        return {
            "file_name": self.file_name,
            "row_number": self.row_number,
            "line_number": self.line_number,
        }


@dataclass(frozen=True)
class RuleResult:
    """Result from one data-quality rule evaluation."""

    rule_id: str
    rule_name: str
    severity: Severity
    category: RuleCategory
    dataset: str
    passed: bool
    message: str
    source_location: SourceLocation | None = None
    field_name: str | None = None
    offending_value: JsonValue = None
    remediation: str | None = None

    def to_dict(self) -> dict[str, JsonValue]:
        """Return a JSON-serialisable representation."""

        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "severity": self.severity,
            "category": self.category,
            "dataset": self.dataset,
            "passed": self.passed,
            "message": self.message,
            "source_location": self.source_location.to_dict() if self.source_location else None,
            "field_name": self.field_name,
            "offending_value": self.offending_value,
            "remediation": self.remediation,
        }


def failed_rule(
    rule_id: str,
    rule_name: str,
    severity: Severity,
    category: RuleCategory,
    dataset: str,
    message: str,
    *,
    source_location: SourceLocation | None = None,
    field_name: str | None = None,
    offending_value: JsonValue = None,
    remediation: str | None = None,
) -> RuleResult:
    """Create a failed rule result with stable fields."""

    return RuleResult(
        rule_id=rule_id,
        rule_name=rule_name,
        severity=severity,
        category=category,
        dataset=dataset,
        passed=False,
        message=message,
        source_location=source_location,
        field_name=field_name,
        offending_value=offending_value,
        remediation=remediation,
    )
