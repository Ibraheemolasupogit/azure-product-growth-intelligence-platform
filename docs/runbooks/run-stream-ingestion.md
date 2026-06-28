# Run Stream Ingestion Simulation

Run the local clickstream streaming simulation:

```bash
python3 -m product_growth_intelligence ingest-stream \
  --source data/samples/nexaflow/clickstream_events.jsonl \
  --output-root data/interim \
  --quality-root outputs/quality \
  --micro-batch-size 25 \
  --fixed-ingestion-time 2026-01-01T00:00:00Z
```

The command reads events sequentially, processes deterministic micro-batches, validates each event against the clickstream contract and taxonomy, writes accepted and quarantine JSONL outputs, and produces a quality report plus stream metrics.

This is a local simulation of streaming ingestion logic. It does not connect to Azure Event Hubs and does not use real sleeps in tests.
