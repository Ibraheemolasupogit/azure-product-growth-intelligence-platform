# Reporting Governance

Milestone 11 reporting artifacts are governed synthetic-data outputs designed for Power BI handoff and portfolio review.

## Rules

- Use `metric-dictionary.csv` as the certified metric-definition source.
- Keep reporting outputs reproducible from committed evidence.
- Preserve synthetic-data disclaimers in dashboard, semantic, and governance artifacts.
- Record lineage from source evidence to reporting tables and semantic outputs.
- Compare manifest checksums before promoting any reporting artifact.
- Treat churn outputs as risk indicators, not automated adverse decisions.
- Treat recommendation metrics as offline ranking evidence, not probabilities.
- Treat segment labels as analytical interpretations, not causal identities.

## Access and Sensitivity

Current data sensitivity is synthetic non-customer data. Future real tenant use would require workspace role review, row-level security design, owner approval, sensitivity labels, data-retention rules, and security review before publication.

## Promotion Path

The intended future path is local validation, curated storage, certified semantic model, report workspace, leadership app, refresh monitoring, and Purview lineage. The repository does not deploy those services in Milestone 11.
