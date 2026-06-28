from pytest import CaptureFixture

from product_growth_intelligence.cli import main


def test_project_info_command_outputs_metadata(capsys: CaptureFixture[str]):
    exit_code = main(["project-info", "--environment", "local"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Azure Product Growth Intelligence Platform" in captured.out
    assert "environment: local" in captured.out
