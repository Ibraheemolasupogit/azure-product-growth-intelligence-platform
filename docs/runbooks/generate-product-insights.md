# Generate Product Insights

This runbook explains how to run the deterministic Milestone 10 product insight assistant.

## Run Locally

```bash
python3 -m product_growth_intelligence generate-product-insights \
  --evidence-root docs/evidence \
  --output-root outputs/genai/product-insights \
  --provider deterministic_template \
  --fixed-run-time 2026-01-02T00:00:00Z
```

The default evidence path uses committed milestone evidence and does not require raw trusted datasets, Azure credentials, or network access.

## Useful Options

- `--run-id` sets a stable output run ID.
- `--include-milestone` may be repeated for a subset of Milestones 4-9.
- `--provider deterministic_template` is the implemented offline provider.
- `--provider azure_openai_placeholder` records future Azure OpenAI adapter metadata without calling Azure.
- `--validate-only` validates configuration and required evidence without writing reports.
- `--overwrite` is required for non-empty output directories.

## Evidence

Generate the committed portfolio evidence:

```bash
make generate-product-insights-sample
make verify-product-insight-evidence
```

The verification target regenerates `docs/evidence/milestone-10/` and fails if deterministic evidence changes unexpectedly.

## Interpretation

Outputs are synthetic-data summaries, not live GenAI responses. The assistant creates deterministic reports from parsed evidence and guardrails. It does not implement chat, Power BI assets, Azure OpenAI calls, vector search, deployed agents, or automated product decisions.
