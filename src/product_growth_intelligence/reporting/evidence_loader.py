"""Load prior milestone evidence for reporting outputs."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, cast

from product_growth_intelligence.ingestion.fingerprints import file_sha256

EvidenceValue = str | list[dict[str, Any]] | dict[str, Any]
EvidenceArtifact = dict[str, object]

REQUIRED_REPORTING_EVIDENCE: dict[int, tuple[str, ...]] = {
    4: ("funnel-summary.csv", "funnel-stage-metrics.csv", "funnel-dropoff-analysis.csv"),
    5: ("cohort-summary.csv", "retention-matrix.csv", "resurrection-analysis.csv"),
    6: ("evaluation-metrics.json", "threshold-analysis.csv", "feature-importance.csv"),
    7: ("segment-profiles.csv", "cluster-candidate-metrics.csv", "segmentation-lineage.json"),
    8: ("model-comparison.csv", "catalogue-coverage.csv", "metrics-by-k.csv"),
    9: ("decision-summary.csv", "guardrail-results.csv", "power-analysis.csv"),
    10: ("grounded-insights.json", "risk-and-caveat-register.csv", "assistant-lineage.json"),
}


def load_reporting_evidence(evidence_root: Path) -> dict[str, EvidenceArtifact]:
    """Load compact evidence artifacts needed by the reporting layer."""

    loaded: dict[str, EvidenceArtifact] = {}
    for milestone, filenames in REQUIRED_REPORTING_EVIDENCE.items():
        milestone_dir = evidence_root / f"milestone-{milestone}"
        if not milestone_dir.exists():
            msg = f"Missing evidence directory: {milestone_dir}."
            raise FileNotFoundError(msg)
        for filename in filenames:
            path = milestone_dir / filename
            if not path.exists():
                msg = f"Missing required reporting evidence artifact: {path}."
                raise FileNotFoundError(msg)
            key = f"milestone_{milestone}/{filename}"
            loaded[key] = {
                "artifact_id": key,
                "path": str(path),
                "milestone": milestone,
                "filename": filename,
                "checksum": file_sha256(path),
                "content": _read_artifact(path),
            }
    return loaded


def artifact_rows(evidence: dict[str, EvidenceArtifact], artifact_id: str) -> list[dict[str, Any]]:
    """Return a CSV evidence artifact as rows."""

    value = evidence[artifact_id]["content"]
    if not isinstance(value, list):
        msg = f"Evidence artifact {artifact_id} is not tabular."
        raise TypeError(msg)
    return value


def artifact_list(evidence: dict[str, EvidenceArtifact], artifact_id: str) -> list[dict[str, Any]]:
    """Return a list-shaped evidence artifact."""

    return artifact_rows(evidence, artifact_id)


def artifact_json(evidence: dict[str, EvidenceArtifact], artifact_id: str) -> dict[str, Any]:
    """Return a JSON evidence artifact."""

    value = evidence[artifact_id]["content"]
    if not isinstance(value, dict):
        msg = f"Evidence artifact {artifact_id} is not a JSON object."
        raise TypeError(msg)
    return value


def _read_artifact(path: Path) -> EvidenceValue:
    if path.suffix == ".json":
        return cast("EvidenceValue", json.loads(path.read_text(encoding="utf-8")))
    if path.suffix == ".csv":
        with path.open(encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    return path.read_text(encoding="utf-8")
