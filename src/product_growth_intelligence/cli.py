"""Command line interface for foundation checks."""

from argparse import ArgumentParser, Namespace
from datetime import date
from pathlib import Path

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

    parser.print_help()
    return 0
