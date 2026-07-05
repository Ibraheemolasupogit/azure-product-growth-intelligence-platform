# Run Recommendation Baseline

This runbook explains how to run the local Milestone 8 governed recommendation baseline against trusted ingestion outputs.

## Prerequisites

Install the project and generate trusted accepted data:

```bash
make install
make generate-sample
python3 -m product_growth_intelligence ingest-batch \
  --source data/samples/nexaflow \
  --output-root /tmp/pgi-recommendation/interim \
  --quality-root /tmp/pgi-recommendation/quality \
  --run-id recommendation-source \
  --fixed-ingestion-time 2026-01-01T00:00:00Z \
  --overwrite
```

## Run the Baseline

```bash
python3 -m product_growth_intelligence build-recommendations \
  --input-dir /tmp/pgi-recommendation/interim/recommendation-source \
  --output-root outputs/models/recommendations \
  --run-id recommendation-sample \
  --snapshot-time 2025-03-31T23:59:59Z \
  --lookback-days 56 \
  --holdout-days 28 \
  --fixed-run-time 2026-01-02T00:00:00Z \
  --overwrite
```

The command writes runtime outputs under `outputs/models/recommendations/recommendation-sample/`.

Useful options:

- `--model` may be repeated to run a subset of `global_popularity`, `recent_popularity`, `segment_popularity`, and `item_item_cf`.
- `--top-k` accepts a comma-separated list such as `1,3,5,10`.
- `--minimum-user-interactions` and `--minimum-item-interactions` control sparse-data thresholds.
- `--no-segments` disables segment-aware reconstruction.
- `--validate-only` checks trusted input compatibility and configuration without writing recommendation outputs.

## Evidence

Generate the committed portfolio evidence:

```bash
make build-recommendations-sample
make verify-recommendation-evidence
```

The verification target regenerates evidence and fails if `docs/evidence/milestone-8/` changes unexpectedly.

## Expected Outputs

Runtime outputs include:

- `user-item-interactions.csv`
- `candidate-items.jsonl`
- `recommendations.csv`
- `recommendation-reasons.jsonl`
- `model-comparison.csv`
- `offline-metrics.json`
- `metrics-by-k.csv`
- `segment-metrics.csv`
- `cold-start-metrics.json`
- `item-similarity.csv`
- `catalogue-coverage.csv`
- `model-metadata.json`
- `run-diagnostics.json`
- `recommendation-manifest.json`
- `recommendation-lineage.json`
- `recommendation-card.md`

Full runtime files stay ignored under `outputs/`. Only concise evidence is committed.

## Interpretation

Recommendations are offline ranked suggestions from synthetic data. They are not probabilities, not causal estimates, and not production treatment policies. Before production use, product teams would need human catalogue review, privacy review, online experimentation, monitoring, rollback plans, and production-grade serving architecture.
