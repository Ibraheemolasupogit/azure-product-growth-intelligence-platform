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


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "project-info":
        return _project_info(args)
    if args.command == "generate-data":
        return _generate_data(args)

    parser.print_help()
    return 0
