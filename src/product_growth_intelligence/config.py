"""Small configuration helpers for Milestone 1."""

from dataclasses import dataclass
from pathlib import Path

SUPPORTED_ENVIRONMENTS = frozenset({"base", "local", "azure-dev", "azure-test", "azure-prod"})


@dataclass(frozen=True)
class ProjectPaths:
    """Repository-relative paths used by the local reference implementation."""

    root: Path
    configs: Path
    data: Path
    outputs: Path
    reports: Path

    @classmethod
    def from_root(cls, root: Path) -> "ProjectPaths":
        resolved_root = root.resolve()
        return cls(
            root=resolved_root,
            configs=resolved_root / "configs",
            data=resolved_root / "data",
            outputs=resolved_root / "outputs",
            reports=resolved_root / "reports",
        )


def validate_environment_name(environment: str) -> str:
    """Validate and normalize an environment name."""

    normalized = environment.strip().lower()
    if normalized not in SUPPORTED_ENVIRONMENTS:
        allowed = ", ".join(sorted(SUPPORTED_ENVIRONMENTS))
        msg = f"Unsupported environment '{environment}'. Expected one of: {allowed}."
        raise ValueError(msg)
    return normalized


def config_file_for_environment(config_dir: Path, environment: str) -> Path:
    """Return the expected config file path for a supported environment."""

    normalized = validate_environment_name(environment)
    file_name = "azure.example.yaml" if normalized.startswith("azure-") else f"{normalized}.yaml"
    return config_dir / file_name
