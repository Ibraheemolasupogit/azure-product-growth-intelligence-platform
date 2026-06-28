"""Schema-drift detection for ingestion contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from product_growth_intelligence.validation.contracts import DatasetContract
from product_growth_intelligence.validation.rule_models import (
    RuleResult,
    SourceLocation,
    failed_rule,
)

SchemaPolicy = Literal["strict", "compatible", "report-only"]


@dataclass(frozen=True)
class SchemaDriftFinding:
    """A classified schema-drift finding."""

    dataset: str
    drift_type: str
    field_name: str
    severity: str
    message: str

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-ready representation."""

        return {
            "dataset": self.dataset,
            "drift_type": self.drift_type,
            "field_name": self.field_name,
            "severity": self.severity,
            "message": self.message,
        }


def detect_schema_drift(
    contract: DatasetContract,
    observed_fields: tuple[str, ...],
    policy: SchemaPolicy,
    source_file: str,
) -> tuple[list[SchemaDriftFinding], list[RuleResult]]:
    """Detect field-level drift according to the configured policy."""

    expected = set(contract.field_names)
    observed = set(observed_fields)
    findings: list[SchemaDriftFinding] = []
    rules: list[RuleResult] = []

    for field_name in sorted(expected - observed):
        drift_type = (
            "missing_required_column"
            if field_name in contract.required_fields
            else "missing_optional_column"
        )
        severity = "error" if field_name in contract.required_fields else "warning"
        finding = SchemaDriftFinding(
            dataset=contract.dataset,
            drift_type=drift_type,
            field_name=field_name,
            severity=severity,
            message=f"Expected field '{field_name}' is missing from {contract.filename}.",
        )
        findings.append(finding)
        if severity == "error" or policy == "strict":
            rules.append(
                failed_rule(
                    "SCHEMA_FIELD_MISSING",
                    "Expected field is present",
                    "error",
                    "schema",
                    contract.dataset,
                    finding.message,
                    source_location=SourceLocation(source_file),
                    field_name=field_name,
                    remediation="Regenerate the source extract or update the governed contract.",
                )
            )

    for field_name in sorted(observed - expected):
        finding = SchemaDriftFinding(
            dataset=contract.dataset,
            drift_type="additive_unknown_column",
            field_name=field_name,
            severity="warning" if policy == "report-only" else "error",
            message=f"Unexpected field '{field_name}' appears in {contract.filename}.",
        )
        findings.append(finding)
        if policy in {"strict", "compatible"}:
            rules.append(
                failed_rule(
                    "SCHEMA_FIELD_UNEXPECTED",
                    "Unexpected fields follow policy",
                    "error",
                    "schema_drift",
                    contract.dataset,
                    finding.message,
                    source_location=SourceLocation(source_file),
                    field_name=field_name,
                    remediation="Remove the field or add a reviewed optional contract field.",
                )
            )
    return findings, rules
