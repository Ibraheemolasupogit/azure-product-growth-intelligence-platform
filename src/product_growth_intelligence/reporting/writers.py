"""Output writers for reporting artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def write_json(path: Path, value: object) -> None:
    """Write stable JSON."""

    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    """Write stable CSV using the union of row fields."""

    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, lines: list[str]) -> None:
    """Write Markdown lines with a final newline."""

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def normalise_number(value: object) -> object:
    """Convert numeric strings to report-friendly numbers when possible."""

    if value is None:
        return ""
    if not isinstance(value, str):
        return value
    if value == "":
        return ""
    try:
        number = float(value)
    except ValueError:
        return value
    if number.is_integer():
        return int(number)
    return round(number, 6)


def markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> list[str]:
    """Build a compact Markdown table."""

    header = "| " + " | ".join(columns) + " |"
    rule = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(str(row.get(column, "")) for column in columns) + " |" for row in rows
    ]
    return [header, rule, *body]
