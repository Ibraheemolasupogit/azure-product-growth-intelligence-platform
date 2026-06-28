"""Focused record-level ingestion quality rules."""

from __future__ import annotations

from product_growth_intelligence.data_generation.catalogues import (
    EVENT_TAXONOMY,
    EXPERIMENT_CATALOGUE,
)
from product_growth_intelligence.data_generation.models import Record
from product_growth_intelligence.validation.contracts import DatasetContract
from product_growth_intelligence.validation.rule_models import (
    RuleResult,
    SourceLocation,
    failed_rule,
)


def validate_record(
    contract: DatasetContract,
    record: Record,
    location: SourceLocation,
) -> list[RuleResult]:
    """Validate one normalised record against domain and schema rules."""

    failures: list[RuleResult] = []
    for field in contract.fields:
        value = record.get(field.name)
        if value is None:
            continue
        if field.identifier_prefix and not str(value).startswith(field.identifier_prefix):
            failures.append(
                failed_rule(
                    "IDENTIFIER_FORMAT_INVALID",
                    "Identifier follows synthetic format",
                    "error",
                    "validity",
                    contract.dataset,
                    f"Field '{field.name}' must start with {field.identifier_prefix}.",
                    source_location=location,
                    field_name=field.name,
                    offending_value=str(value),
                    remediation="Use the governed synthetic identifier format.",
                )
            )
        if field.allowed_values is not None and str(value) not in field.allowed_values:
            failures.append(
                failed_rule(
                    "CATEGORICAL_VALUE_INVALID",
                    "Categorical value is known",
                    "error",
                    "validity",
                    contract.dataset,
                    f"Field '{field.name}' contains unknown value '{value}'.",
                    source_location=location,
                    field_name=field.name,
                    offending_value=str(value),
                    remediation="Map the value to the catalogue or update the contract.",
                )
            )

    if contract.dataset == "clickstream_events":
        failures.extend(_validate_event(record, location))
    if contract.dataset == "experiment_assignments":
        failures.extend(_validate_assignment(record, location))
    return failures


def _validate_event(record: Record, location: SourceLocation) -> list[RuleResult]:
    event_name = str(record.get("event_name"))
    if event_name not in EVENT_TAXONOMY:
        return []
    failures: list[RuleResult] = []
    spec = EVENT_TAXONOMY[event_name]
    if record.get("feature_name") != spec.feature_name:
        failures.append(
            failed_rule(
                "EVENT_FEATURE_MISMATCH",
                "Event feature matches taxonomy",
                "error",
                "validity",
                "clickstream_events",
                f"Event {event_name} has incompatible feature {record.get('feature_name')}.",
                source_location=location,
                field_name="feature_name",
                offending_value=str(record.get("feature_name")),
                remediation="Correct feature_name to the taxonomy value.",
            )
        )
    if record.get("journey_stage") != spec.journey_stage:
        failures.append(
            failed_rule(
                "EVENT_STAGE_MISMATCH",
                "Event journey stage matches taxonomy",
                "error",
                "validity",
                "clickstream_events",
                f"Event {event_name} has incompatible journey stage.",
                source_location=location,
                field_name="journey_stage",
                offending_value=str(record.get("journey_stage")),
            )
        )
    properties = record.get("properties")
    if not isinstance(properties, dict):
        failures.append(
            failed_rule(
                "EVENT_PROPERTIES_INVALID",
                "Event properties are a JSON object",
                "error",
                "schema",
                "clickstream_events",
                "Event properties must be a JSON object.",
                source_location=location,
                field_name="properties",
            )
        )
    experiment_id = record.get("experiment_id")
    variant = record.get("experiment_variant")
    if experiment_id is not None:
        if str(experiment_id) not in EXPERIMENT_CATALOGUE:
            failures.append(
                failed_rule(
                    "EXPERIMENT_ID_INVALID",
                    "Experiment ID is known",
                    "error",
                    "validity",
                    "clickstream_events",
                    f"Unknown experiment {experiment_id}.",
                    source_location=location,
                    field_name="experiment_id",
                    offending_value=str(experiment_id),
                )
            )
        elif variant not in EXPERIMENT_CATALOGUE[str(experiment_id)]["variants"]:
            failures.append(
                failed_rule(
                    "EXPERIMENT_VARIANT_INVALID",
                    "Experiment variant is valid",
                    "error",
                    "validity",
                    "clickstream_events",
                    f"Invalid variant {variant} for {experiment_id}.",
                    source_location=location,
                    field_name="experiment_variant",
                    offending_value=str(variant),
                )
            )
    return failures


def _validate_assignment(record: Record, location: SourceLocation) -> list[RuleResult]:
    experiment_id = str(record.get("experiment_id"))
    variant = str(record.get("variant"))
    if (
        experiment_id in EXPERIMENT_CATALOGUE
        and variant in EXPERIMENT_CATALOGUE[experiment_id]["variants"]
    ):
        return []
    return [
        failed_rule(
            "EXPERIMENT_VARIANT_INVALID",
            "Experiment assignment variant is valid",
            "error",
            "validity",
            "experiment_assignments",
            f"Invalid variant {variant} for {experiment_id}.",
            source_location=location,
            field_name="variant",
            offending_value=variant,
        )
    ]
