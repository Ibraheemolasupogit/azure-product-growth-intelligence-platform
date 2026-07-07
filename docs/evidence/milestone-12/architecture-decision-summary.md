# Architecture Decision Summary

- Local-first execution is the default so review requires no Azure subscription.
- Synthetic NexaFlow data avoids customer-data, PII, and credential risk.
- Each analytical layer emits deterministic evidence, lineage, and manifests.
- Azure mappings are documented but not executed.
- Power BI readiness is represented by CSV outputs and semantic docs, not `.pbix`.
- Future production deployment requires identity, monitoring, Purview, RLS,
  networking, cost review, and operating ownership.
