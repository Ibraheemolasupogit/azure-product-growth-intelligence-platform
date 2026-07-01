# Train Churn Model

Use this runbook to train the local Milestone 6 churn model from trusted Milestone 3 accepted outputs.

First create trusted input:

```bash
python3 -m product_growth_intelligence ingest-batch \
  --source data/samples/nexaflow \
  --output-root /tmp/pgi-m6/interim \
  --quality-root /tmp/pgi-m6/quality \
  --run-id milestone6-source \
  --fixed-ingestion-time 2026-01-01T00:00:00Z \
  --overwrite
```

Then train:

```bash
python3 -m product_growth_intelligence train-churn-model \
  --input-dir /tmp/pgi-m6/interim/milestone6-source \
  --output-root /tmp/pgi-m6/churn \
  --run-id milestone6-sample \
  --lookback-days 28 \
  --label-window-days 28 \
  --analysis-end 2025-03-31T23:59:59Z \
  --fixed-run-time 2026-01-02T00:00:00Z \
  --overwrite
```

Expected outputs include `churn-definition.json`, `feature-catalogue.json`, `snapshot-labels.jsonl`, `feature-matrix.csv`, `dataset-splits.csv`, `training-metrics.json`, `evaluation-metrics.json`, `threshold-analysis.csv`, `predictions.csv`, `feature-importance.csv`, `model-metadata.json`, `model-card.md`, `run-diagnostics.json`, `model-manifest.json`, and `model-lineage.json`.

Generate committed evidence with:

```bash
make verify-churn-evidence
```

The model uses synthetic data only. Treat the outputs as a reproducible portfolio demonstration, not as a production model or automated decision system.
