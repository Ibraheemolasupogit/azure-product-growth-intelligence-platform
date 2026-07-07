# Build Reporting Layer Runbook

Use this runbook to build deterministic Power BI-ready reporting outputs from committed evidence.

## Build Runtime Outputs

```bash
python3 -m product_growth_intelligence build-reporting-layer \
  --evidence-root docs/evidence \
  --output-root outputs/reporting/powerbi \
  --fixed-run-time 2026-01-02T00:00:00Z
```

Use `--run-id` to choose a stable output folder, `--include-domain` to filter facts by reporting domain, `--validate-only` to validate without writing files, and `--overwrite` to replace a non-empty output directory.

The command refuses to overwrite non-empty outputs unless `--overwrite` is supplied.

## Generate Portfolio Evidence

```bash
make build-reporting-layer-sample
make verify-reporting-evidence
```

The verification target regenerates `docs/evidence/milestone-11/` and fails if the deterministic evidence changes.

## Expected Outputs

The run writes reporting tables, semantic-model metadata, metric dictionary, dashboard specs, visual specs, refresh plan, governance notes, executive summary, diagnostics, lineage, and manifest files. Runtime outputs belong under `outputs/reporting/powerbi/<run_id>/`.

No Power BI deployment, Fabric deployment, Azure resource provisioning, or `.pbix` creation is performed.
