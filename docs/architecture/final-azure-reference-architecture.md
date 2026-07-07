# Final Azure Reference Architecture

The Azure Product Growth Intelligence Platform is a production-style local reference implementation for product analytics, growth intelligence, governed ML, experimentation, deterministic product insights, and Power BI-ready reporting.

The default repository is local-first and Azure-mappable. It does not deploy Azure resources, create credentials, call Azure services, create `.pbix` files, or run live infrastructure automation.

## Platform Layers

1. Synthetic source generation creates deterministic NexaFlow users, sessions, events, subscriptions, feature usage, experiment assignments, and feedback.
2. Event ingestion and validation treat all source files as untrusted input and publish accepted or quarantined records with quality evidence.
3. Trusted data zone stores accepted local outputs that map to curated ADLS Gen2 zones in a future deployment.
4. Funnel analytics computes governed product journey conversion and drop-off metrics.
5. Retention analytics builds cohorts, retention matrices, lifecycle statuses, and resurrection evidence.
6. Churn prediction trains leakage-safe local models with chronological splits and model cards.
7. User segmentation builds rule-based and KMeans behavioural groups with stability checks.
8. Recommendation baseline compares deterministic offline ranking approaches.
9. Experiment analysis evaluates fixed-window A/B tests with SRM, guardrails, power, and decision rules.
10. Product insight assistant converts committed evidence into deterministic, governed summaries.
11. Reporting and semantic layer emits Power BI-ready tables, semantic model documentation, metrics, visual specs, lineage, and refresh guidance.
12. Azure deployment mapping documents how local components can be deployed later after governance review.

## Azure Reference Mapping

| Platform capability | Azure service mapping |
| --- | --- |
| Event ingestion | Azure Event Hubs |
| Raw and trusted storage | Azure Data Lake Storage Gen2 |
| Batch orchestration | Azure Data Factory or Synapse pipelines |
| Stream processing | Azure Functions or Stream Analytics |
| Analytical transformations | Azure Synapse Analytics |
| ML training and batch scoring | Azure Machine Learning |
| GenAI insight layer | Azure AI Foundry / Azure OpenAI |
| Semantic reporting | Power BI |
| Governance and lineage | Microsoft Purview |
| Secrets | Azure Key Vault |
| Identity | Microsoft Entra ID / Managed Identity |
| Monitoring | Azure Monitor / Application Insights |
| CI quality gates | GitHub Actions |

## Review Positioning

The architecture is suitable for portfolio and interview review because every layer has deterministic local evidence, tests, and documentation. A production team would still need landing-zone approval, identity design, network boundaries, cost controls, Purview registration, Power BI workspace governance, and operational runbooks before live deployment.
