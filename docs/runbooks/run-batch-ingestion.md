# Run Batch Ingestion

Run the committed sample through the local batch ingestion pipeline:

```bash
python3 -m product_growth_intelligence ingest-batch \
  --source data/samples/nexaflow \
  --output-root data/interim \
  --quality-root outputs/quality \
  --fixed-ingestion-time 2026-01-01T00:00:00Z
```

Useful options:

- `--run-id`: provide a deterministic ingestion run ID.
- `--schema-policy`: choose `strict`, `compatible`, or `report-only`.
- `--duplicate-policy`: choose `reject`, `keep-first`, or `keep-last`.
- `--max-quarantine-rate`: fail the run if quarantine exceeds the threshold.
- `--overwrite`: replace an existing non-empty run directory.
- `--validate-only`: run validation without writing final artefacts.

Outputs are written under:

```text
data/interim/<ingestion_run_id>/
outputs/quality/<ingestion_run_id>/
```

The command writes accepted records, quarantine records, `quality-report.json`, `quality-report.md`, `lineage.json`, `ingestion-manifest.json`, and `run-metrics.json`. Runtime outputs are gitignored.

To regenerate the concise committed evidence artefacts:

```bash
python3 scripts/generate_ingestion_evidence.py
```

To verify the committed evidence is deterministic:

```bash
make verify-ingestion-evidence
```
