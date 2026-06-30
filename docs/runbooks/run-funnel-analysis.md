# Run Funnel Analysis

First create trusted Milestone 3 accepted outputs:

```bash
python3 -m product_growth_intelligence ingest-batch \
  --source data/samples/nexaflow \
  --output-root /tmp/pgi-funnels/interim \
  --quality-root /tmp/pgi-funnels/quality \
  --run-id milestone4-source \
  --fixed-ingestion-time 2026-01-01T00:00:00Z \
  --overwrite
```

Then run governed funnel analytics:

```bash
python3 -m product_growth_intelligence analyse-funnels \
  --input-dir /tmp/pgi-funnels/interim/milestone4-source \
  --output-root /tmp/pgi-funnels/funnels \
  --run-id milestone4-analysis \
  --fixed-analysis-time 2026-01-02T00:00:00Z \
  --overwrite
```

Useful options:

- `--funnel`: analyse one or more selected funnel IDs.
- `--sequence-policy`: choose `strict` or `flexible`; both preserve ordered required stages in Milestone 4.
- `--segment`: request descriptive segment dimensions.
- `--suppression-threshold`: suppress small segment cells.
- `--validate-only`: validate and calculate without writing final artefacts.

Runtime outputs are written beneath `outputs/analytics/funnels/<analysis_run_id>/` or the configured output root.

Regenerate committed evidence:

```bash
python3 scripts/generate_funnel_evidence.py
```

Verify deterministic evidence:

```bash
make verify-funnel-evidence
```
