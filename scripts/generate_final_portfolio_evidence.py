"""Generate deterministic Milestone 12 final portfolio evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

EVIDENCE_DIR = Path("docs/evidence/milestone-12")
FIXED_REVIEW_TIMESTAMP = "2026-01-02T00:00:00Z"
MILESTONE_STATUS = {f"milestone_{number}": "completed" for number in range(1, 13)}

AZURE_SERVICE_MAPPING: list[dict[str, str]] = [
    {
        "platform_capability": "Event ingestion",
        "local_implementation": "Batch ingestion and JSONL stream simulation",
        "azure_service_mapping": "Azure Event Hubs",
    },
    {
        "platform_capability": "Raw and trusted storage",
        "local_implementation": "data/raw, data/interim, committed sample evidence",
        "azure_service_mapping": "Azure Data Lake Storage Gen2",
    },
    {
        "platform_capability": "Batch orchestration",
        "local_implementation": "Makefile and deterministic scripts",
        "azure_service_mapping": "Azure Data Factory or Synapse pipelines",
    },
    {
        "platform_capability": "Stream processing",
        "local_implementation": "Deterministic micro-batch simulation",
        "azure_service_mapping": "Azure Functions or Stream Analytics",
    },
    {
        "platform_capability": "Analytical transformations",
        "local_implementation": "Typed Python analytics modules",
        "azure_service_mapping": "Azure Synapse Analytics",
    },
    {
        "platform_capability": "ML training and batch scoring",
        "local_implementation": "Deterministic churn, segmentation, and recommendation workflows",
        "azure_service_mapping": "Azure Machine Learning",
    },
    {
        "platform_capability": "GenAI insight layer",
        "local_implementation": "Deterministic local product insight assistant",
        "azure_service_mapping": "Azure AI Foundry / Azure OpenAI",
    },
    {
        "platform_capability": "Semantic reporting",
        "local_implementation": "Power BI-ready CSVs and semantic model docs",
        "azure_service_mapping": "Power BI",
    },
    {
        "platform_capability": "Governance and lineage",
        "local_implementation": "Evidence manifests, checksums, lineage JSON",
        "azure_service_mapping": "Microsoft Purview",
    },
    {
        "platform_capability": "Secrets",
        "local_implementation": "No secrets; placeholder configuration only",
        "azure_service_mapping": "Azure Key Vault",
    },
    {
        "platform_capability": "Identity",
        "local_implementation": "Local developer identity only",
        "azure_service_mapping": "Microsoft Entra ID / Managed Identity",
    },
    {
        "platform_capability": "Monitoring",
        "local_implementation": "Diagnostics, quality reports, run summaries",
        "azure_service_mapping": "Azure Monitor / Application Insights",
    },
    {
        "platform_capability": "CI quality gates",
        "local_implementation": "Lint, formatting, mypy, tests, evidence checks",
        "azure_service_mapping": "GitHub Actions",
    },
]

REQUIRED_SOURCE_FILES = (
    "README.md",
    ".github/workflows/ci.yml",
    "Makefile",
    "docs/architecture/final-azure-reference-architecture.md",
    "docs/architecture/deployment-options.md",
    "docs/architecture/local-to-azure-mapping.md",
    "docs/architecture/platform-operating-model.md",
    "docs/architecture/security-governance-and-lineage.md",
    "docs/architecture/cost-and-environment-assumptions.md",
    "docs/architecture/diagrams.md",
    "docs/portfolio/portfolio-walkthrough.md",
    "docs/portfolio/interview-explanation-guide.md",
    "docs/portfolio/recruiter-summary.md",
    "docs/portfolio/technical-review-guide.md",
    "docs/portfolio/evidence-index.md",
    "docs/evidence/README.md",
    "infrastructure/README.md",
    "infrastructure/bicep/README.md",
    "infrastructure/terraform/README.md",
)


def main() -> int:
    """Generate Milestone 12 evidence files."""

    validate_sources()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    _write_text(EVIDENCE_DIR / "final-platform-summary.md", final_platform_summary())
    _write_json(EVIDENCE_DIR / "azure-service-mapping.json", azure_service_mapping())
    _write_text(
        EVIDENCE_DIR / "architecture-decision-summary.md",
        architecture_decision_summary(),
    )
    _write_text(EVIDENCE_DIR / "portfolio-review-checklist.md", portfolio_review_checklist())
    _write_json(EVIDENCE_DIR / "repo-health-summary.json", repo_health_summary())
    _write_json(EVIDENCE_DIR / "final-lineage-overview.json", final_lineage_overview())
    _write_text(EVIDENCE_DIR / "deployment-readiness-notes.md", deployment_readiness_notes())
    _write_json(EVIDENCE_DIR / "milestone-12-manifest.json", milestone_manifest())
    print(f"Milestone 12 final portfolio evidence written to {EVIDENCE_DIR}")
    return 0


def validate_sources() -> None:
    """Validate source docs required by Milestone 12 evidence."""

    missing = [path for path in REQUIRED_SOURCE_FILES if not Path(path).exists()]
    if missing:
        msg = f"Missing required Milestone 12 source file(s): {', '.join(missing)}"
        raise FileNotFoundError(msg)


def azure_service_mapping() -> dict[str, object]:
    """Return machine-readable Azure service mapping evidence."""

    return {
        "generated_at": FIXED_REVIEW_TIMESTAMP,
        "deployment_status": "not_deployed",
        "local_first": True,
        "mapping": AZURE_SERVICE_MAPPING,
    }


def repo_health_summary() -> dict[str, object]:
    """Return deterministic repository health evidence."""

    evidence_folders = sorted(
        path.name for path in Path("docs/evidence").glob("milestone-*") if path.is_dir()
    )
    return {
        "generated_at": FIXED_REVIEW_TIMESTAMP,
        "latest_known_milestone_status": MILESTONE_STATUS,
        "evidence_folder_count": len(evidence_folders),
        "evidence_folders": evidence_folders,
        "key_commands": [
            "make quality",
            "make verify-portfolio",
            "python3 -m product_growth_intelligence project-info",
            (
                "python3 -m product_growth_intelligence build-reporting-layer "
                "--evidence-root docs/evidence"
            ),
        ],
        "test_command": "python3 -m pytest",
        "quality_command": "make quality",
        "ci_workflow_path": ".github/workflows/ci.yml",
        "local_first_status": "local-first and Azure-mappable",
        "azure_deployment_status": "not deployed",
        "powerbi_deployment_status": "not deployed; semantic outputs only",
        "synthetic_data_status": "synthetic NexaFlow data only",
        "known_limitations": [
            "No live Azure resources are provisioned.",
            "No Power BI .pbix file is created.",
            "Models are synthetic-data demonstrations and require production review.",
            "GenAI assistant is deterministic by default and does not call Azure OpenAI.",
        ],
        "generated_artifact_checksums": output_checksums(
            exclude=("milestone-12-manifest.json", "repo-health-summary.json")
        ),
    }


def final_lineage_overview() -> dict[str, object]:
    """Return the final platform lineage overview."""

    steps = [
        "synthetic data",
        "raw landing",
        "ingestion validation",
        "trusted accepted data",
        "funnel analytics",
        "retention analytics",
        "churn prediction",
        "user segmentation",
        "recommendation baseline",
        "experiment analysis",
        "product insights",
        "Power BI-ready reporting",
        "portfolio evidence",
    ]
    return {
        "generated_at": FIXED_REVIEW_TIMESTAMP,
        "lineage_steps": steps,
        "source_policy": "synthetic_only",
        "default_execution": "local_first",
        "azure_deployment_performed": False,
        "powerbi_deployment_performed": False,
        "human_review_required_for_production": True,
    }


def milestone_manifest() -> dict[str, object]:
    """Return the Milestone 12 evidence manifest."""

    return {
        "milestone": 12,
        "milestone_name": "Azure architecture, deployment options and portfolio polish",
        "generated_at": FIXED_REVIEW_TIMESTAMP,
        "status": "completed",
        "source_files_validated": list(REQUIRED_SOURCE_FILES),
        "output_checksums": output_checksums(),
        "azure_deployment_performed": False,
        "powerbi_file_created": False,
        "synthetic_data_only": True,
    }


def final_platform_summary() -> str:
    """Return readable final platform summary evidence."""

    return "\n".join(
        [
            "# Final Platform Summary",
            "",
            "The Azure Product Growth Intelligence Platform is a production-style local",
            "reference implementation for synthetic product analytics, governed ML,",
            "experimentation, deterministic product insights, and Power BI-ready reporting.",
            "",
            "Milestones 1-12 are complete. The repository is local-first and Azure-mappable;",
            "it is not a live deployed Azure platform.",
            "",
            "Primary reviewer paths:",
            "- README for executive overview and quickstart.",
            "- docs/architecture for final Azure architecture and deployment options.",
            "- docs/portfolio for interview and technical-review walkthroughs.",
            "- docs/evidence for deterministic milestone evidence.",
            "",
        ]
    )


def architecture_decision_summary() -> str:
    """Return concise final architecture decision summary."""

    return "\n".join(
        [
            "# Architecture Decision Summary",
            "",
            "- Local-first execution is the default so review requires no Azure subscription.",
            "- Synthetic NexaFlow data avoids customer-data, PII, and credential risk.",
            "- Each analytical layer emits deterministic evidence, lineage, and manifests.",
            "- Azure mappings are documented but not executed.",
            "- Power BI readiness is represented by CSV outputs and semantic docs, not `.pbix`.",
            "- Future production deployment requires identity, monitoring, Purview, RLS,",
            "  networking, cost review, and operating ownership.",
            "",
        ]
    )


def portfolio_review_checklist() -> str:
    """Return final portfolio review checklist."""

    return "\n".join(
        [
            "# Portfolio Review Checklist",
            "",
            "- Read `README.md` for the platform overview.",
            "- Review `docs/architecture/final-azure-reference-architecture.md`.",
            "- Inspect `docs/portfolio/technical-review-guide.md` for reviewer routes.",
            "- Run `make quality` for linting, typing, tests, and coverage.",
            "- Run `make verify-final-evidence` for Milestone 12 determinism.",
            "- Confirm no Azure deployment workflow or `.pbix` file exists.",
            "- Confirm evidence folders `milestone-3` through `milestone-12` are present.",
            "",
        ]
    )


def deployment_readiness_notes() -> str:
    """Return deployment readiness notes."""

    return "\n".join(
        [
            "# Deployment Readiness Notes",
            "",
            "The repository is deployment-ready in design documentation only. It does not",
            "include executable Azure deployment jobs, service principals, subscription IDs,",
            "tenant IDs, production secrets, or Power BI files.",
            "",
            "Before live deployment, a team would need Azure landing-zone approval, managed",
            "identity design, Key Vault-backed configuration, private networking decisions,",
            "Purview registration, Power BI workspace governance, RLS design, cost controls,",
            "model-risk review, and operational support ownership.",
            "",
        ]
    )


def output_checksums(
    exclude: tuple[str, ...] = ("milestone-12-manifest.json",),
) -> dict[str, str]:
    """Return checksums for generated Milestone 12 artifacts."""

    checksums: dict[str, str] = {}
    if not EVIDENCE_DIR.exists():
        return checksums
    excluded = set(exclude)
    for path in sorted(EVIDENCE_DIR.iterdir()):
        if path.is_file() and path.name not in excluded:
            checksums[path.name] = file_sha256(path)
    return checksums


def file_sha256(path: Path) -> str:
    """Return a file SHA-256 checksum."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
