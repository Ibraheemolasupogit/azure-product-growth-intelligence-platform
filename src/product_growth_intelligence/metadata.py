"""Project metadata exposed to the CLI and tests."""

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

PACKAGE_DISTRIBUTION_NAME = "azure-product-growth-intelligence-platform"
PROJECT_NAME = "Azure Product Growth Intelligence Platform"


@dataclass(frozen=True)
class ProjectMetadata:
    """Lightweight install metadata."""

    name: str
    package: str
    version: str
    default_environment: str


def get_project_metadata() -> ProjectMetadata:
    """Return metadata without importing heavyweight optional dependencies."""

    try:
        package_version = version(PACKAGE_DISTRIBUTION_NAME)
    except PackageNotFoundError:
        package_version = "0.1.0"

    return ProjectMetadata(
        name=PROJECT_NAME,
        package="product_growth_intelligence",
        version=package_version,
        default_environment="local",
    )
