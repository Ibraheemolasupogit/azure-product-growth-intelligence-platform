"""Command line interface for foundation checks."""

from argparse import ArgumentParser, Namespace
from datetime import date
from pathlib import Path

from product_growth_intelligence.analytics import FunnelAnalysisConfig, run_funnel_analysis
from product_growth_intelligence.analytics.funnel_models import DEFAULT_SEGMENT_DIMENSIONS
from product_growth_intelligence.analytics.retention import (
    RetentionAnalysisConfig,
    run_retention_analysis,
)
from product_growth_intelligence.analytics.retention.models import DEFAULT_RETENTION_SEGMENTS
from product_growth_intelligence.config import validate_environment_name
from product_growth_intelligence.data_generation import (
    default_generation_config,
    generate_datasets,
    write_datasets,
)
from product_growth_intelligence.data_generation.models import GenerationConfig
from product_growth_intelligence.ingestion import IngestionConfig, run_batch_ingestion
from product_growth_intelligence.ingestion.streaming import run_stream_ingestion
from product_growth_intelligence.metadata import get_project_metadata


def build_parser() -> ArgumentParser:
    """Build the command parser."""

    parser = ArgumentParser(prog="pgi", description="Product growth intelligence utilities.")
    subparsers = parser.add_subparsers(dest="command")

    info = subparsers.add_parser("project-info", help="Display project metadata.")
    info.add_argument("--environment", default="local", help="Environment name to validate.")

    generate = subparsers.add_parser("generate-data", help="Generate synthetic NexaFlow data.")
    generate.add_argument("--profile", default="sample", choices=("sample", "development"))
    generate.add_argument("--seed", type=int, default=None)
    generate.add_argument("--users", type=int, default=None)
    generate.add_argument("--start-date", type=date.fromisoformat, default=None)
    generate.add_argument("--end-date", type=date.fromisoformat, default=None)
    generate.add_argument("--output-dir", type=Path, default=None)
    generate.add_argument("--overwrite", action="store_true")
    generate.add_argument("--validate-only", action="store_true")

    batch = subparsers.add_parser("ingest-batch", help="Run local batch ingestion.")
    batch.add_argument("--source", type=Path, required=True)
    batch.add_argument("--run-id", default=None)
    batch.add_argument("--output-root", type=Path, default=Path("data/interim"))
    batch.add_argument("--quality-root", type=Path, default=Path("outputs/quality"))
    batch.add_argument(
        "--schema-policy", choices=("strict", "compatible", "report-only"), default="strict"
    )
    batch.add_argument(
        "--duplicate-policy", choices=("reject", "keep-first", "keep-last"), default="reject"
    )
    batch.add_argument("--contract-version", default="2026-06-milestone-3")
    batch.add_argument("--max-quarantine-rate", type=float, default=0.0)
    batch.add_argument("--fixed-ingestion-time", default=None)
    batch.add_argument("--overwrite", action="store_true")
    batch.add_argument("--validate-only", action="store_true")
    batch.add_argument("--no-checksum-enforcement", action="store_true")

    stream = subparsers.add_parser("ingest-stream", help="Run local clickstream simulation.")
    stream.add_argument("--source", type=Path, required=True)
    stream.add_argument("--run-id", default=None)
    stream.add_argument("--output-root", type=Path, default=Path("data/interim"))
    stream.add_argument("--quality-root", type=Path, default=Path("outputs/quality"))
    stream.add_argument(
        "--schema-policy", choices=("strict", "compatible", "report-only"), default="strict"
    )
    stream.add_argument(
        "--duplicate-policy", choices=("reject", "keep-first", "keep-last"), default="reject"
    )
    stream.add_argument("--contract-version", default="2026-06-milestone-3")
    stream.add_argument("--max-quarantine-rate", type=float, default=1.0)
    stream.add_argument("--micro-batch-size", type=int, default=25)
    stream.add_argument("--fixed-ingestion-time", default=None)
    stream.add_argument("--overwrite", action="store_true")
    stream.add_argument("--validate-only", action="store_true")

    funnels = subparsers.add_parser("analyse-funnels", help="Run governed funnel analytics.")
    funnels.add_argument("--input-dir", type=Path, required=True)
    funnels.add_argument("--output-root", type=Path, default=Path("outputs/analytics/funnels"))
    funnels.add_argument("--run-id", default=None)
    funnels.add_argument("--funnel", action="append", default=[])
    funnels.add_argument("--analysis-start", default="2025-01-01T00:00:00Z")
    funnels.add_argument("--analysis-end", default="2025-06-30T23:59:59Z")
    funnels.add_argument("--attempt-policy", choices=("first-entry",), default="first-entry")
    funnels.add_argument("--sequence-policy", choices=("strict", "flexible"), default="strict")
    funnels.add_argument("--segment", action="append", default=[])
    funnels.add_argument("--suppression-threshold", type=int, default=5)
    funnels.add_argument("--fixed-analysis-time", default=None)
    funnels.add_argument("--overwrite", action="store_true")
    funnels.add_argument("--validate-only", action="store_true")

    retention = subparsers.add_parser("analyse-retention", help="Run retention analytics.")
    retention.add_argument("--input-dir", type=Path, required=True)
    retention.add_argument("--output-root", type=Path, default=Path("outputs/analytics/retention"))
    retention.add_argument("--run-id", default=None)
    retention.add_argument("--definition", action="append", default=[])
    retention.add_argument("--time-grain", choices=("daily", "weekly", "monthly"), default="weekly")
    retention.add_argument("--analysis-start", default="2025-01-01T00:00:00Z")
    retention.add_argument("--analysis-end", default="2025-06-30T23:59:59Z")
    retention.add_argument("--horizon", type=int, default=8)
    retention.add_argument("--segment", action="append", default=[])
    retention.add_argument("--suppression-threshold", type=int, default=5)
    retention.add_argument("--inactivity-threshold", type=int, default=2)
    retention.add_argument("--churn-threshold", type=int, default=4)
    retention.add_argument("--fixed-analysis-time", default=None)
    retention.add_argument("--overwrite", action="store_true")
    retention.add_argument("--validate-only", action="store_true")

    return parser


def _project_info(args: Namespace) -> int:
    metadata = get_project_metadata()
    environment = validate_environment_name(args.environment)
    print(f"name: {metadata.name}")
    print(f"package: {metadata.package}")
    print(f"version: {metadata.version}")
    print(f"environment: {environment}")
    return 0


def _generate_data(args: Namespace) -> int:
    config = default_generation_config(args.profile, args.output_dir)
    config = GenerationConfig(
        profile=config.profile,
        user_count=args.users if args.users is not None else config.user_count,
        start_date=args.start_date if args.start_date is not None else config.start_date,
        end_date=args.end_date if args.end_date is not None else config.end_date,
        seed=args.seed if args.seed is not None else config.seed,
        output_dir=args.output_dir if args.output_dir is not None else config.output_dir,
        timezone=config.timezone,
        persona_distribution=config.persona_distribution,
        acquisition_channel_distribution=config.acquisition_channel_distribution,
        country_distribution=config.country_distribution,
        feedback_probability=config.feedback_probability,
        include_generation_timestamp=config.include_generation_timestamp,
    )
    datasets = generate_datasets(config)

    if args.validate_only:
        print("Synthetic data validation succeeded.")
        for dataset_name, records in datasets.by_name().items():
            print(f"{dataset_name}: {len(records)} rows")
        return 0

    result = write_datasets(datasets, config, overwrite=args.overwrite)
    print(f"Synthetic NexaFlow data written to: {result.output_dir}")
    print(f"manifest: {result.manifest_path}")
    for dataset_name, row_count in result.row_counts.items():
        print(f"{dataset_name}: {row_count} rows")
    return 0


def _ingest_batch(args: Namespace) -> int:
    config = IngestionConfig(
        source=args.source,
        output_root=args.output_root,
        quality_root=args.quality_root,
        run_id=args.run_id,
        mode="batch",
        contract_version=args.contract_version,
        schema_policy=args.schema_policy,
        duplicate_policy=args.duplicate_policy,
        checksum_enforcement=not args.no_checksum_enforcement,
        max_quarantine_rate=args.max_quarantine_rate,
        fixed_ingestion_time=args.fixed_ingestion_time,
        overwrite=args.overwrite,
        validate_only=args.validate_only,
    )
    result = run_batch_ingestion(config)
    print(f"Batch ingestion run: {result.run_id}")
    print(f"status: {result.status}")
    print(f"accepted: {result.accepted_count}")
    print(f"quarantined: {result.quarantined_count}")
    print(f"output: {result.output_dir}")
    print(f"quality: {result.quality_dir}")
    return 0 if result.status != "failed" else 1


def _ingest_stream(args: Namespace) -> int:
    config = IngestionConfig(
        source=args.source,
        output_root=args.output_root,
        quality_root=args.quality_root,
        run_id=args.run_id,
        mode="stream",
        contract_version=args.contract_version,
        schema_policy=args.schema_policy,
        duplicate_policy=args.duplicate_policy,
        max_quarantine_rate=args.max_quarantine_rate,
        fixed_ingestion_time=args.fixed_ingestion_time,
        overwrite=args.overwrite,
        validate_only=args.validate_only,
        stream_micro_batch_size=args.micro_batch_size,
    )
    result = run_stream_ingestion(config)
    print(f"Stream ingestion run: {result.run_id}")
    print(f"status: {result.status}")
    print(f"accepted: {result.accepted_count}")
    print(f"quarantined: {result.quarantined_count}")
    print(f"output: {result.output_dir}")
    print(f"quality: {result.quality_dir}")
    return 0 if result.status != "failed" else 1


def _analyse_funnels(args: Namespace) -> int:
    config = FunnelAnalysisConfig(
        input_dir=args.input_dir,
        output_root=args.output_root,
        run_id=args.run_id,
        analysis_start=args.analysis_start,
        analysis_end=args.analysis_end,
        attempt_policy=args.attempt_policy,
        sequence_policy=args.sequence_policy,
        enabled_funnels=tuple(args.funnel),
        segment_dimensions=tuple(args.segment) if args.segment else DEFAULT_SEGMENT_DIMENSIONS,
        suppression_threshold=args.suppression_threshold,
        fixed_analysis_time=args.fixed_analysis_time,
        overwrite=args.overwrite,
        validate_only=args.validate_only,
    )
    result = run_funnel_analysis(config)
    completed = sum(1 for attempt in result.attempts if attempt.attempt_status == "completed")
    print(f"Funnel analysis run: {result.run_id}")
    print(f"status: {result.status}")
    print(f"attempts: {len(result.attempts)}")
    print(f"completed: {completed}")
    print(f"output: {result.output_dir}")
    return 0 if result.status != "failed" else 1


def _analyse_retention(args: Namespace) -> int:
    config = RetentionAnalysisConfig(
        input_dir=args.input_dir,
        output_root=args.output_root,
        run_id=args.run_id,
        enabled_definitions=tuple(args.definition),
        time_grain=args.time_grain,
        analysis_start=args.analysis_start,
        analysis_end=args.analysis_end,
        horizon=args.horizon,
        segment_dimensions=tuple(args.segment) if args.segment else DEFAULT_RETENTION_SEGMENTS,
        suppression_threshold=args.suppression_threshold,
        inactivity_threshold=args.inactivity_threshold,
        churn_threshold=args.churn_threshold,
        fixed_analysis_time=args.fixed_analysis_time,
        overwrite=args.overwrite,
        validate_only=args.validate_only,
    )
    result = run_retention_analysis(config)
    print(f"Retention analysis run: {result.run_id}")
    print(f"status: {result.status}")
    print(f"memberships: {len(result.memberships)}")
    print(f"user_periods: {len(result.user_periods)}")
    print(f"output: {result.output_dir}")
    return 0 if result.status != "failed" else 1


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "project-info":
        return _project_info(args)
    if args.command == "generate-data":
        return _generate_data(args)
    if args.command == "ingest-batch":
        return _ingest_batch(args)
    if args.command == "ingest-stream":
        return _ingest_stream(args)
    if args.command == "analyse-funnels":
        return _analyse_funnels(args)
    if args.command == "analyse-retention":
        return _analyse_retention(args)

    parser.print_help()
    return 0
