"""Safe CSV and JSONL parsers for untrusted source files."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from product_growth_intelligence.data_generation.models import JsonValue, Record
from product_growth_intelligence.ingestion.models import ParsedRecord
from product_growth_intelligence.validation.contracts import DatasetContract, FieldContract
from product_growth_intelligence.validation.rule_models import SourceLocation, failed_rule
from product_growth_intelligence.validation.schema_drift import SchemaPolicy, detect_schema_drift


def parse_dataset(
    source_dir: Path,
    contract: DatasetContract,
    schema_policy: SchemaPolicy,
) -> tuple[list[ParsedRecord], list[Any], list[Any]]:
    """Parse a dataset and return parsed records, schema findings, and file rules."""

    path = source_dir / contract.filename
    if contract.file_format == "csv":
        return parse_csv(path, contract, schema_policy)
    return parse_jsonl(path, contract, schema_policy)


def parse_csv(
    path: Path,
    contract: DatasetContract,
    schema_policy: SchemaPolicy,
) -> tuple[list[ParsedRecord], list[Any], list[Any]]:
    """Parse a UTF-8 CSV file with explicit header validation."""

    file_rules: list[Any] = []
    records: list[ParsedRecord] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        sample = handle.readline()
        if not sample:
            file_rules.append(
                failed_rule(
                    "FILE_EMPTY",
                    "File has a header",
                    "critical",
                    "file_integrity",
                    contract.dataset,
                    f"{contract.filename} is empty.",
                    source_location=SourceLocation(contract.filename),
                )
            )
            return records, [], file_rules
        header = next(csv.reader([sample]))
        duplicates = sorted({name for name in header if header.count(name) > 1})
        if duplicates:
            file_rules.append(
                failed_rule(
                    "CSV_DUPLICATE_HEADER",
                    "CSV headers are unique",
                    "critical",
                    "schema",
                    contract.dataset,
                    f"Duplicate CSV header: {duplicates[0]}.",
                    source_location=SourceLocation(contract.filename),
                    field_name=duplicates[0],
                )
            )
            return records, [], file_rules
        findings, drift_rules = detect_schema_drift(
            contract, tuple(header), schema_policy, contract.filename
        )
        file_rules.extend(drift_rules)
        handle.seek(0)
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):
            location = SourceLocation(contract.filename, row_number=row_number)
            normalised, errors = _normalise_record(row, contract, location)
            records.append(
                ParsedRecord(
                    dataset=contract.dataset,
                    source_file=contract.filename,
                    source_location=location,
                    raw_record=dict(row),
                    record=normalised if not errors else None,
                    parse_errors=tuple(errors),
                )
            )
    return records, findings, file_rules


def parse_jsonl(
    path: Path,
    contract: DatasetContract,
    schema_policy: SchemaPolicy,
) -> tuple[list[ParsedRecord], list[Any], list[Any]]:
    """Parse a JSONL file with line-number tracking and quarantineable errors."""

    records: list[ParsedRecord] = []
    file_rules: list[Any] = []
    findings: list[Any] = []
    observed_fields: tuple[str, ...] | None = None
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            location = SourceLocation(contract.filename, line_number=line_number)
            stripped = line.strip()
            if not stripped:
                records.append(
                    ParsedRecord(
                        dataset=contract.dataset,
                        source_file=contract.filename,
                        source_location=location,
                        raw_record="",
                        record=None,
                        parse_errors=(
                            failed_rule(
                                "JSONL_BLANK_LINE",
                                "JSONL contains non-empty records",
                                "warning",
                                "schema",
                                contract.dataset,
                                "Blank JSONL lines are ignored and reported.",
                                source_location=location,
                            ),
                        ),
                    )
                )
                continue
            try:
                raw = json.loads(stripped)
            except json.JSONDecodeError as exc:
                records.append(
                    ParsedRecord(
                        dataset=contract.dataset,
                        source_file=contract.filename,
                        source_location=location,
                        raw_record=stripped,
                        record=None,
                        parse_errors=(
                            failed_rule(
                                "JSONL_MALFORMED",
                                "JSONL record is valid JSON",
                                "error",
                                "schema",
                                contract.dataset,
                                f"Malformed JSON at line {line_number}: {exc.msg}.",
                                source_location=location,
                                remediation="Re-emit the event as one valid JSON object per line.",
                            ),
                        ),
                    )
                )
                continue
            if not isinstance(raw, dict):
                records.append(
                    ParsedRecord(
                        dataset=contract.dataset,
                        source_file=contract.filename,
                        source_location=location,
                        raw_record=_json_value(raw),
                        record=None,
                        parse_errors=(
                            failed_rule(
                                "JSONL_NON_OBJECT",
                                "JSONL record is an object",
                                "error",
                                "schema",
                                contract.dataset,
                                "JSONL records must be objects.",
                                source_location=location,
                            ),
                        ),
                    )
                )
                continue
            if observed_fields is None:
                observed_fields = tuple(raw)
                findings, drift_rules = detect_schema_drift(
                    contract, observed_fields, schema_policy, contract.filename
                )
                file_rules.extend(drift_rules)
            normalised, errors = _normalise_record(raw, contract, location)
            records.append(
                ParsedRecord(
                    dataset=contract.dataset,
                    source_file=contract.filename,
                    source_location=location,
                    raw_record=_json_value(raw),
                    record=normalised if not errors else None,
                    parse_errors=tuple(errors),
                )
            )
    return records, findings, file_rules


def _normalise_record(
    raw: dict[str, Any],
    contract: DatasetContract,
    location: SourceLocation,
) -> tuple[Record, list[Any]]:
    fields = contract.field_by_name()
    record: Record = {}
    errors: list[Any] = []
    for field in contract.fields:
        value = raw.get(field.name)
        if _is_null(value):
            if field.nullable:
                record[field.name] = None
                continue
            errors.append(
                failed_rule(
                    "FIELD_REQUIRED",
                    "Required values are populated",
                    "error",
                    "completeness",
                    contract.dataset,
                    f"Required field '{field.name}' is blank or missing.",
                    source_location=location,
                    field_name=field.name,
                    offending_value=None if value is None else str(value),
                    remediation="Supply the required field before ingestion.",
                )
            )
            continue
        converted, error_message = _convert_value(value, field)
        if error_message:
            errors.append(
                failed_rule(
                    "FIELD_TYPE_INVALID",
                    "Field value matches contract type",
                    "error",
                    "validity",
                    contract.dataset,
                    error_message,
                    source_location=location,
                    field_name=field.name,
                    offending_value=_safe_value(value),
                    remediation="Correct the value or update the governed contract.",
                )
            )
            continue
        record[field.name] = converted
    for field_name in sorted(set(raw) - set(fields)):
        if field_name not in record:
            record[field_name] = raw[field_name]
    return record, errors


def _convert_value(value: object, field: FieldContract) -> tuple[object, str | None]:
    try:
        if field.field_type == "string":
            return str(value), None
        if field.field_type == "boolean":
            return _parse_bool(value), None
        if field.field_type == "integer":
            parsed = int(str(value))
            return parsed, _range_error(parsed, field)
        if field.field_type == "decimal":
            parsed_decimal = Decimal(str(value))
            return parsed_decimal, _range_error(float(parsed_decimal), field)
        if field.field_type == "date":
            text = str(value)
            datetime.strptime(text, "%Y-%m-%d")
            return text, None
        if field.field_type == "timestamp":
            text = str(value)
            datetime.fromisoformat(text.replace("Z", "+00:00"))
            return text, None
        if field.field_type == "object":
            if isinstance(value, dict):
                return value, None
            return None, f"Field '{field.name}' must be a JSON object."
    except (ValueError, TypeError, InvalidOperation):
        return None, f"Field '{field.name}' cannot be parsed as {field.field_type}."
    return None, f"Unsupported field type {field.field_type}."


def _parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    msg = "Expected True or False."
    raise ValueError(msg)


def _range_error(value: int | float, field: FieldContract) -> str | None:
    if field.minimum is not None and value < field.minimum:
        return f"Field '{field.name}' is below minimum {field.minimum}."
    if field.maximum is not None and value > field.maximum:
        return f"Field '{field.name}' is above maximum {field.maximum}."
    return None


def _is_null(value: object) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _safe_value(value: object) -> JsonValue:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, dict):
        return {str(key): _safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    return str(value)


def _json_value(value: object) -> JsonValue:
    return _safe_value(value)
