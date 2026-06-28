"""Command line interface for foundation checks."""

from argparse import ArgumentParser, Namespace

from product_growth_intelligence.config import validate_environment_name
from product_growth_intelligence.metadata import get_project_metadata


def build_parser() -> ArgumentParser:
    """Build the command parser."""

    parser = ArgumentParser(prog="pgi", description="Product growth intelligence utilities.")
    subparsers = parser.add_subparsers(dest="command")

    info = subparsers.add_parser("project-info", help="Display project metadata.")
    info.add_argument("--environment", default="local", help="Environment name to validate.")

    return parser


def _project_info(args: Namespace) -> int:
    metadata = get_project_metadata()
    environment = validate_environment_name(args.environment)
    print(f"name: {metadata.name}")
    print(f"package: {metadata.package}")
    print(f"version: {metadata.version}")
    print(f"environment: {environment}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "project-info":
        return _project_info(args)

    parser.print_help()
    return 0
