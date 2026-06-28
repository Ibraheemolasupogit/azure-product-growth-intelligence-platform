# Ingestion Quality Report: milestone-3-sample

Overall status: **passed**

## Summary
- source_records: 964
- accepted_records: 964
- quarantined_records: 0
- warning_count: 0
- error_count: 0
- critical_count: 0

## Dataset Scorecard

| Dataset | Source | Accepted | Quarantine | Pass rate |
| --- | ---: | ---: | ---: | ---: |
| users | 12 | 12 | 0 | 1.0 |
| sessions | 84 | 84 | 0 | 1.0 |
| clickstream_events | 591 | 591 | 0 | 1.0 |
| feature_usage | 244 | 244 | 0 | 1.0 |
| subscriptions | 18 | 18 | 0 | 1.0 |
| experiment_assignments | 12 | 12 | 0 | 1.0 |
| customer_feedback | 3 | 3 | 0 | 1.0 |

## Remediation

Inspect quarantine JSONL records, correct malformed source extracts, and rerun with the same run ID plus --overwrite once the source is fixed.
