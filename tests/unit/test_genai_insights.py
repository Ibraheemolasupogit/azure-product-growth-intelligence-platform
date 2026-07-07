import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from product_growth_intelligence.genai import (
    ProductInsightConfig,
    build_insight_inputs,
    generate_grounded_insights,
    load_evidence,
    run_governance_checks,
    run_product_insights,
)
from product_growth_intelligence.genai.providers import provider_for

FIXED_RUN_TIME = "2026-01-02T00:00:00Z"


def test_evidence_loading_and_prompt_package_are_deterministic():
    evidence = load_evidence(Path("docs/evidence"), (4, 5, 6, 7, 8, 9))
    inputs = build_insight_inputs(evidence)
    provider = provider_for("deterministic_template")
    prompt = provider.build_prompt_package(inputs)

    assert len(evidence) >= 19
    assert inputs["recommendations"]["selected_model"] == "segment_popularity"
    assert prompt["llm_call_performed"] is False
    assert prompt["generation_mode"] == "deterministic_template"


def test_missing_and_malformed_evidence_fail(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_evidence(tmp_path / "missing", (4,))

    evidence_root = tmp_path / "evidence"
    shutil.copytree("docs/evidence", evidence_root)
    (evidence_root / "milestone-6" / "evaluation-metrics.json").write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_evidence(evidence_root, (6,))


def test_grounded_insights_and_governance_guardrails():
    evidence = load_evidence(Path("docs/evidence"), (4, 5, 6, 7, 8, 9))
    inputs = build_insight_inputs(evidence)
    prompt = provider_for("deterministic_template").build_prompt_package(inputs)
    insights = generate_grounded_insights(inputs, "deterministic_template")
    checks = run_governance_checks(insights, evidence, prompt)

    assert len(insights) == 8
    assert checks["overall_status"] == "passed"
    assert all(insight["supporting_evidence"] for insight in insights)
    assert all("synthetic NexaFlow" in insight["synthetic_data_disclaimer"] for insight in insights)
    recommendation = next(
        insight for insight in insights if insight["insight_type"] == "recommendation"
    )
    assert "rankings, not probabilities" in " ".join(recommendation["caveats"])
    segment = next(insight for insight in insights if insight["insight_type"] == "segmentation")
    assert "analytical interpretations" in " ".join(segment["caveats"])
    experiment = next(insight for insight in insights if insight["insight_type"] == "experiment")
    assert "sample-size" in " ".join(experiment["caveats"])


def test_governance_blocks_unsupported_claims():
    evidence = load_evidence(Path("docs/evidence"), (4, 5, 6, 7, 8, 9))
    inputs = build_insight_inputs(evidence)
    prompt = provider_for("deterministic_template").build_prompt_package(inputs)
    insights = generate_grounded_insights(inputs, "deterministic_template")
    bad = dict(insights[0])
    bad["summary"] = "This caused guaranteed growth."
    bad["supporting_evidence"] = []

    checks = run_governance_checks([bad, *insights[1:]], evidence, prompt)

    assert checks["overall_status"] == "failed"
    assert checks["all_insights_have_sources"] is False
    assert checks["causal_language_blocked"] is False


def test_azure_placeholder_provider_makes_no_call():
    evidence = load_evidence(Path("docs/evidence"), (4, 5, 6, 7, 8, 9))
    inputs = build_insight_inputs(evidence)

    prompt = provider_for("azure_openai_placeholder").build_prompt_package(inputs)

    assert prompt["provider"] == "azure_openai_placeholder"
    assert prompt["llm_call_performed"] is False
    assert prompt["endpoint_env_var"] == "AZURE_OPENAI_ENDPOINT"


def test_product_insight_outputs_and_overwrite_refusal(tmp_path: Path):
    config = _config(tmp_path, "sample")

    result = run_product_insights(config)

    assert result.status == "passed"
    assert result.insight_count == 8
    output_dir = tmp_path / "insights" / "sample"
    assert (output_dir / "assistant-run-manifest.json").exists()
    manifest = json.loads((output_dir / "assistant-run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["llm_call_performed"] is False
    assert "grounded-insights.json" in manifest["output_checksums"]
    checks = json.loads((output_dir / "insight-governance-checks.json").read_text(encoding="utf-8"))
    assert checks["overall_status"] == "passed"
    with pytest.raises(FileExistsError):
        run_product_insights(config)


def test_product_insight_cli_success(tmp_path: Path):
    command = [
        sys.executable,
        "-m",
        "product_growth_intelligence",
        "generate-product-insights",
        "--evidence-root",
        "docs/evidence",
        "--output-root",
        str(tmp_path / "insights"),
        "--run-id",
        "cli",
        "--provider",
        "deterministic_template",
        "--fixed-run-time",
        FIXED_RUN_TIME,
    ]

    result = subprocess.run(command, check=False, capture_output=True, text=True)

    assert result.returncode == 0
    assert "status: passed" in result.stdout
    assert "insights: 8" in result.stdout


def test_product_insight_evidence_generation_is_deterministic():
    result = subprocess.run(
        [sys.executable, "scripts/generate_product_insight_evidence.py"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert Path("docs/evidence/milestone-10/assistant-run-manifest.json").exists()


def _config(tmp_path: Path, run_id: str) -> ProductInsightConfig:
    return ProductInsightConfig(
        evidence_root=Path("docs/evidence"),
        output_root=tmp_path / "insights",
        run_id=run_id,
        provider="deterministic_template",
        fixed_run_time=FIXED_RUN_TIME,
    )
