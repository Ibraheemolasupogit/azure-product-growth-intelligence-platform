# Platform Operating Model

The operating model separates analytics ownership, engineering ownership, governance review, and future cloud operations.

## Roles

| Role | Responsibilities |
| --- | --- |
| Product analytics | Funnel, retention, product-health metrics, metric dictionary |
| Growth analytics | Cohorts, experiments, interpretation caveats |
| Data engineering | Ingestion, validation, data contracts, lineage |
| ML engineering | Churn, segmentation, recommendations, model evidence |
| AI engineering | Product insight assistant, prompt package governance |
| Analytics engineering | Semantic reporting, Power BI-ready outputs, refresh checks |
| Security and governance | Synthetic-only policy, access model, production readiness review |

## Local Operating Cadence

- Run `make quality` before review.
- Regenerate milestone evidence with dedicated Makefile targets.
- Use fixed timestamps for deterministic evidence.
- Treat docs and evidence as reviewable artifacts.
- Keep runtime outputs under ignored folders.

## Future Azure Operating Cadence

A future deployed environment would need release approvals, monitoring ownership, data-quality alerting, cost review, model-risk review, Power BI workspace promotion, and incident response. Those activities are documented only and not automated in this repository.
