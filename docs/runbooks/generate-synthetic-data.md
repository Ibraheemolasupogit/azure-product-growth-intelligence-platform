# Generate Synthetic Data

Use the CLI to generate deterministic NexaFlow datasets.

## Regenerate the Committed Sample

```bash
make generate-sample
```

This writes all seven required datasets and `manifest.json` under `data/samples/nexaflow`.

## Generate a Local Raw Run

```bash
python3 -m product_growth_intelligence generate-data \
  --profile development \
  --output-dir data/raw/development-run \
  --overwrite
```

Generated raw runs under `data/raw/` are ignored by Git by default.

## Useful Options

```bash
python3 -m product_growth_intelligence generate-data \
  --profile sample \
  --seed 123 \
  --users 20 \
  --start-date 2025-01-01 \
  --end-date 2025-03-31 \
  --output-dir data/raw/example-run \
  --overwrite
```

Use `--validate-only` to generate and validate in memory without writing files.

## Overwrite Protection

The CLI refuses to write into an existing non-empty output directory unless `--overwrite` is supplied.

## Determinism

For the same profile, seed, simulation period, and user count, record IDs and dataset contents are stable. The manifest includes file checksums and omits wall-clock creation timestamps by default to keep tests deterministic.

