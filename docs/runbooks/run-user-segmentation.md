# Run User Segmentation

First create trusted accepted input:

```bash
python3 -m product_growth_intelligence ingest-batch \
  --source data/samples/nexaflow \
  --output-root /tmp/pgi-m7/interim \
  --quality-root /tmp/pgi-m7/quality \
  --run-id milestone7-source \
  --fixed-ingestion-time 2026-01-01T00:00:00Z \
  --overwrite
```

Then run segmentation:

```bash
python3 -m product_growth_intelligence segment-users \
  --input-dir /tmp/pgi-m7/interim/milestone7-source \
  --output-root /tmp/pgi-m7/segmentation \
  --run-id milestone7-segmentation \
  --snapshot-time 2025-06-30T23:59:59Z \
  --lookback-days 56 \
  --fixed-run-time 2026-01-02T00:00:00Z \
  --overwrite
```

Runtime outputs include snapshots, feature matrix, rule-based assignments, cluster candidate metrics, stability, cluster assignments, profiles, centroids, PCA coordinates, metadata, diagnostics, manifest, lineage, and segment card.

Generate committed portfolio evidence with:

```bash
make verify-segmentation-evidence
```

The evidence uses synthetic data and is intended for reproducible portfolio review only. It does not create recommendations, GenAI names, Power BI files, Azure resources, or live assignment endpoints.
