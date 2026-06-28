from pathlib import Path

import pytest

from product_growth_intelligence.config import (
    ProjectPaths,
    config_file_for_environment,
    validate_environment_name,
)


def test_validate_environment_name_normalizes_supported_value():
    assert validate_environment_name(" LOCAL ") == "local"


def test_validate_environment_name_rejects_unknown_value():
    with pytest.raises(ValueError, match="Unsupported environment"):
        validate_environment_name("production-ish")


def test_config_file_for_azure_environment_uses_example_template():
    assert config_file_for_environment(Path("configs"), "azure-dev") == Path(
        "configs/azure.example.yaml"
    )


def test_project_paths_are_rooted_at_repository_path(tmp_path: Path):
    paths = ProjectPaths.from_root(tmp_path)
    assert paths.configs == tmp_path.resolve() / "configs"
    assert paths.outputs == tmp_path.resolve() / "outputs"
