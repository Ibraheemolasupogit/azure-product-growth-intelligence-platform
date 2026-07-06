# Run Experiment Analysis

This runbook explains how to run the local Milestone 9 governed experiment-analysis workflow.

## Prerequisites

Create trusted accepted data from the committed synthetic sample:

```bash
python3 -m product_growth_intelligence ingest-batch \
  --source data/samples/nexaflow \
  --output-root /tmp/pgi-experiments/interim \
  --quality-root /tmp/pgi-experiments/quality \
  --run-id experiment-source \
  --fixed-ingestion-time 2026-01-01T00:00:00Z \
  --overwrite
```

## Run All Experiments

```bash
python3 -m product_growth_intelligence analyse-experiments \
  --input-dir /tmp/pgi-experiments/interim/experiment-source \
  --output-root outputs/experiments \
  --run-id experiment-sample \
  --analysis-time 2025-06-30T23:59:59Z \
  --fixed-run-time 2026-01-02T00:00:00Z \
  --overwrite
```

## Useful Options

- `--experiment` may be repeated to analyse selected experiment IDs.
- `--population` may be repeated for `intention_to_treat` and `exposed`.
- `--multiple-testing` supports `none`, `bonferroni`, and `benjamini_hochberg`.
- `--segment` may be repeated to select segment dimensions.
- `--suppression-threshold` controls exploratory segment suppression.
- `--validate-only` checks trusted input and configuration without writing outputs.

## Evidence

Generate deterministic portfolio evidence:

```bash
make analyse-experiments-sample
make verify-experiment-evidence
```

The verification target regenerates `docs/evidence/milestone-9/` and fails if evidence changes unexpectedly.

## Interpretation

This workflow is fixed-window offline analysis over synthetic data. Small samples may be underpowered, subgroup effects are exploratory, and decisions should be reviewed by product, data, and risk stakeholders before any rollout. The workflow does not implement online experimentation services, uplift modelling, bandits, GenAI, Power BI, or Azure deployment.
