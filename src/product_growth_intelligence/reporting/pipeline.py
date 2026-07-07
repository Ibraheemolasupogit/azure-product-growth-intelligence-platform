"""Reporting-layer orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from product_growth_intelligence.reporting.dashboard_spec import (
    build_dashboard_pages,
    build_visual_specs,
    dashboard_markdown,
)
from product_growth_intelligence.reporting.evidence_loader import (
    EvidenceArtifact,
    load_reporting_evidence,
)
from product_growth_intelligence.reporting.manifests import build_lineage, build_manifest
from product_growth_intelligence.reporting.metric_dictionary import METRIC_DICTIONARY
from product_growth_intelligence.reporting.models import ReportingLayerConfig, ReportingLayerResult
from product_growth_intelligence.reporting.semantic_model import (
    build_semantic_model,
    semantic_model_markdown,
)
from product_growth_intelligence.reporting.tables import build_reporting_tables
from product_growth_intelligence.reporting.validation import validate_reporting_layer
from product_growth_intelligence.reporting.writers import write_csv, write_json, write_markdown

__all__ = ["ReportingLayerConfig", "ReportingLayerResult", "run_reporting_layer"]


def run_reporting_layer(config: ReportingLayerConfig) -> ReportingLayerResult:
    """Build deterministic Power BI-ready reporting outputs."""

    config.validate()
    run_id = config.run_id or _default_run_id(config)
    output_dir = config.output_root / run_id
    if output_dir.exists() and any(output_dir.iterdir()) and not config.overwrite:
        msg = f"Output directory {output_dir} already exists and is not empty. Pass --overwrite."
        raise FileExistsError(msg)

    evidence = load_reporting_evidence(config.evidence_root)
    tables = _filter_tables(build_reporting_tables(evidence), config.include_domains)
    semantic_model = build_semantic_model(tables)
    pages = build_dashboard_pages()
    visuals = build_visual_specs()
    diagnostics = validate_reporting_layer(evidence, tables, semantic_model, pages, visuals)

    if config.validate_only:
        return ReportingLayerResult(
            run_id=run_id,
            status=str(diagnostics["overall_status"]),
            output_dir=output_dir,
            table_count=len(tables),
            metric_count=len(METRIC_DICTIONARY),
            visual_count=len(visuals),
            diagnostics=diagnostics,
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_outputs(
        output_dir,
        run_id,
        config.fixed_run_time,
        evidence,
        tables,
        semantic_model,
        pages,
        visuals,
        diagnostics,
    )
    return ReportingLayerResult(
        run_id=run_id,
        status=str(diagnostics["overall_status"]),
        output_dir=output_dir,
        table_count=len(tables),
        metric_count=len(METRIC_DICTIONARY),
        visual_count=len(visuals),
        diagnostics=diagnostics,
    )


def _write_outputs(
    output_dir: Path,
    run_id: str,
    fixed_run_time: str | None,
    evidence: dict[str, EvidenceArtifact],
    tables: dict[str, list[dict[str, object]]],
    semantic_model: dict[str, object],
    pages: list[dict[str, object]],
    visuals: list[dict[str, object]],
    diagnostics: dict[str, object],
) -> None:
    for table_name, rows in tables.items():
        write_csv(output_dir / f"{table_name}.csv", rows)
    write_csv(output_dir / "metric-dictionary.csv", METRIC_DICTIONARY)
    write_json(output_dir / "semantic-model.json", semantic_model)
    write_markdown(output_dir / "semantic-model.md", semantic_model_markdown(semantic_model))
    write_json(output_dir / "dashboard-pages.json", pages)
    write_json(output_dir / "visual-specifications.json", visuals)
    write_markdown(output_dir / "dashboard-specification.md", dashboard_markdown(pages, visuals))
    write_markdown(output_dir / "powerbi-refresh-plan.md", _refresh_plan())
    write_markdown(output_dir / "powerbi-governance-notes.md", _governance_notes())
    write_markdown(output_dir / "executive-reporting-summary.md", _executive_summary(tables))
    lineage = build_lineage(evidence, list(tables))
    write_json(output_dir / "reporting-lineage.json", lineage)
    write_json(output_dir / "reporting-diagnostics.json", diagnostics)
    manifest = build_manifest(
        output_dir,
        run_id,
        fixed_run_time or datetime.now(UTC).replace(microsecond=0).isoformat(),
        diagnostics,
    )
    write_json(output_dir / "reporting-manifest.json", manifest)


def _filter_tables(
    tables: dict[str, list[dict[str, object]]], domains: tuple[str, ...]
) -> dict[str, list[dict[str, object]]]:
    if not domains:
        return tables
    filtered: dict[str, list[dict[str, object]]] = {}
    for table_name, rows in tables.items():
        if table_name.startswith("dim_"):
            filtered[table_name] = rows
        else:
            filtered[table_name] = [row for row in rows if row.get("domain_key") in domains]
    return filtered


def _refresh_plan() -> list[str]:
    return [
        "# Power BI Refresh Plan",
        "",
        "1. Rebuild reporting CSVs from committed or certified analytics evidence.",
        "2. Compare `reporting-manifest.json` checksums with the promoted artifact set.",
        "3. Publish CSV outputs to the future ADLS Gen2 curated reporting zone.",
        "4. Refresh the Power BI semantic model from certified reporting tables.",
        "5. Review diagnostics, lineage, and synthetic-data disclaimers before promotion.",
        "",
        "This repository does not deploy Power BI, Fabric, Azure Data Factory, or Azure resources.",
    ]


def _governance_notes() -> list[str]:
    return [
        "# Reporting Governance Notes",
        "",
        "- Data classification: synthetic non-customer NexaFlow evidence.",
        "- Certified metrics: use `metric-dictionary.csv` as the governed definition source.",
        "- Lineage: source evidence and output checksums are recorded in JSON manifests.",
        "- Owner roles: product analytics, growth analytics, data science, recommendations,",
        "  and experiment owners.",
        "- RLS guidance: start with workspace roles; add domain/geography filters only after",
        "  real tenant review.",
        "- Sensitivity: do not mix real customer data into this repository without a",
        "  governance review.",
        "- Versioning: semantic model version is tied to Milestone 11 reporting outputs.",
        "- Promotion path: local validation, curated storage, certified semantic model,",
        "  report workspace, leadership app.",
        "- Future service mapping: Power BI scheduled refresh, Data Factory orchestration,",
        "  Purview lineage, Entra ID access.",
        "",
        "No live Power BI deployment or Azure provisioning is performed.",
    ]


def _executive_summary(tables: dict[str, list[dict[str, object]]]) -> list[str]:
    return [
        "# Executive Reporting Summary",
        "",
        "Milestone 11 converts governed NexaFlow evidence into Power BI-ready reporting artifacts.",
        "The layer includes curated CSV facts and dimensions, a semantic model,",
        "a metric dictionary, dashboard specifications, visual specifications,",
        "refresh guidance, governance notes, lineage,",
        "and manifest checksums.",
        "",
        f"Reporting tables: {len(tables)}.",
        f"Metric definitions: {len(METRIC_DICTIONARY)}.",
        "",
        "All outputs are derived from synthetic committed evidence and remain local-first.",
    ]


def _default_run_id(config: ReportingLayerConfig) -> str:
    if config.fixed_run_time:
        stamp = (
            config.fixed_run_time.replace(":", "")
            .replace("-", "")
            .replace("T", "-")
            .replace("Z", "")
        )
    else:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"powerbi-reporting-{stamp}"
