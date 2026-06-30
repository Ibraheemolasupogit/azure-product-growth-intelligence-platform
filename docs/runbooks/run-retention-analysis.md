# Run Retention Analysis

Create trusted Milestone 3 accepted outputs:

```bash
python3 -m product_growth_intelligence ingest-batch \
  --source data/samples/nexaflow \
  --output-root /tmp/pgi-retention/interim \
  --quality-root /tmp/pgi-retention/quality \
  --run-id milestone5-source \
  --fixed-ingestion-time 2026-01-01T00:00:00Z \
  --overwrite
```

Run weekly retention analytics:

```bash
python3 -m product_growth_intelligence analyse-retention \
  --input-dir /tmp/pgi-retention/interim/milestone5-source \
  --output-root /tmp/pgi-retention/retention \
  --time-grain weekly \
  --fixed-analysis-time 2026-01-02T00:00:00Z \
  --overwrite
```

Useful options:

- `--definition`: run one or more selected definitions.
- `--time-grain`: choose `daily`, `weekly`, or `monthly`.
- `--horizon`: set maximum period index.
- `--segment`: request descriptive segment dimensions.
- `--suppression-threshold`: suppress small cells.
- `--inactivity-threshold` and `--churn-threshold`: configure descriptive lifecycle status.
- `--validate-only`: calculate without writing final artefacts.

Regenerate committed evidence:

```bash
python3 scripts/generate_retention_evidence.py
```

Verify deterministic evidence:

```bash
make verify-retention-evidence
```
