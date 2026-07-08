import json
import subprocess
import sys
from pathlib import Path

from scripts.generate_final_portfolio_evidence import (
    AZURE_SERVICE_MAPPING,
    MILESTONE_STATUS,
    final_lineage_overview,
    repo_health_summary,
)


def test_final_azure_service_mapping_is_complete():
    expected = {
        "Event ingestion",
        "Raw and trusted storage",
        "Batch orchestration",
        "Stream processing",
        "Analytical transformations",
        "ML training and batch scoring",
        "GenAI insight layer",
        "Semantic reporting",
        "Governance and lineage",
        "Secrets",
        "Identity",
        "Monitoring",
        "CI quality gates",
    }

    assert {row["platform_capability"] for row in AZURE_SERVICE_MAPPING} == expected


def test_milestone_status_and_repo_health_summary_are_complete():
    health = repo_health_summary()

    assert {f"milestone_{number}": "completed" for number in range(1, 13)} == MILESTONE_STATUS
    assert health["azure_deployment_status"] == "not deployed"
    assert health["powerbi_deployment_status"] == "not deployed; semantic outputs only"
    assert health["synthetic_data_status"] == "synthetic NexaFlow data only"
    assert int(health["evidence_folder_count"]) >= 10


def test_final_lineage_overview_structure():
    lineage = final_lineage_overview()

    assert lineage["lineage_steps"][0] == "synthetic data"
    assert lineage["lineage_steps"][-1] == "portfolio evidence"
    assert "Power BI-ready reporting" in lineage["lineage_steps"]
    assert lineage["azure_deployment_performed"] is False


def test_final_evidence_generation_and_manifest():
    completed = subprocess.run(
        [sys.executable, "scripts/generate_final_portfolio_evidence.py"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    manifest_path = Path("docs/evidence/milestone-12/milestone-12-manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert manifest["azure_deployment_performed"] is False
    assert "repo-health-summary.json" in manifest["output_checksums"]
    repo_health = json.loads(
        Path("docs/evidence/milestone-12/repo-health-summary.json").read_text(encoding="utf-8")
    )
    assert "repo-health-summary.json" not in repo_health["generated_artifact_checksums"]


def test_evidence_index_and_readme_reference_all_milestones():
    evidence_index = Path("docs/evidence/README.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")

    for number in range(3, 13):
        assert f"milestone-{number}" in evidence_index
    for number in range(1, 13):
        assert f"Milestone {number}" in readme
    assert "Milestone 12 — completed" in readme


def test_ci_contains_no_forbidden_deployment_commands():
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    forbidden = ("az deployment", "terraform apply", "pulumi up", "Power BI Service")

    assert all(command not in workflow for command in forbidden)
    assert "make verify-final-evidence" in workflow
