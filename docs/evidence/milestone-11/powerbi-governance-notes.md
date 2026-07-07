# Reporting Governance Notes

- Data classification: synthetic non-customer NexaFlow evidence.
- Certified metrics: use `metric-dictionary.csv` as the governed definition source.
- Lineage: source evidence and output checksums are recorded in JSON manifests.
- Owner roles: product analytics, growth analytics, data science, recommendations,
  and experiment owners.
- RLS guidance: start with workspace roles; add domain/geography filters only after
  real tenant review.
- Sensitivity: do not mix real customer data into this repository without a
  governance review.
- Versioning: semantic model version is tied to Milestone 11 reporting outputs.
- Promotion path: local validation, curated storage, certified semantic model,
  report workspace, leadership app.
- Future service mapping: Power BI scheduled refresh, Data Factory orchestration,
  Purview lineage, Entra ID access.

No live Power BI deployment or Azure provisioning is performed.
