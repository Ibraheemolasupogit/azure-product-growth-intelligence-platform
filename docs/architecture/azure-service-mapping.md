# Azure Service Mapping

The platform is local-first, but each major component is designed to map cleanly to Azure services when optional deployment work is introduced.

| Capability | Local reference implementation | Azure-native implementation |
| --- | --- | --- |
| Product event ingestion | Local batch ingestion and JSONL stream simulation | Azure Event Hubs |
| Raw storage | `data/raw` | Azure Data Lake Storage Gen2 raw container |
| Trusted interim storage | `data/interim/<run_id>/accepted` | Azure Data Lake Storage Gen2 trusted or curated container |
| Quarantine storage | `data/interim/<run_id>/quarantine` | Azure Data Lake Storage Gen2 quarantine zone |
| Stream processing | Deterministic local micro-batch simulation | Azure Stream Analytics or Azure Functions |
| Analytical serving | Local output tables | Azure Synapse Analytics |
| Funnel transformations | Local governed funnel pipeline | Azure Synapse Analytics |
| Cohort transformations | Local governed retention pipeline | Azure Synapse Analytics |
| Churn feature preparation | Local point-in-time churn feature builder | Azure Synapse Analytics or Azure ML data preparation |
| Recommendation interaction preparation | Local point-in-time interaction and candidate builder | Azure Synapse Analytics or Azure ML data preparation |
| Experiment metric transformations | Local fixed-window experiment metric builder | Azure Synapse Analytics |
| Scheduled analytics | Makefile/CI commands | Azure Data Factory or Synapse pipelines |
| Statistical experiment analysis | Local SciPy-backed inference and decision workflow | Azure Machine Learning jobs or governed Python workloads |
| Product insight generation | Local deterministic template assistant | Azure AI Foundry prompt flow or Azure OpenAI adapter |
| Insight governance checks | Local deterministic safety checks | Azure AI Content Safety and Responsible AI controls |
| Reporting CSV outputs | Local Power BI-ready reporting tables | Azure Data Lake Storage Gen2 curated reporting zone |
| Semantic model documentation | Local semantic-model JSON and Markdown | Power BI semantic model or Tabular model design |
| Metric dictionary | Local governed CSV dictionary | Certified Power BI metrics and governance catalogue |
| Dashboard specification | Local page and visual specs | Power BI report pages |
| Refresh plan | Local runbook and manifest checksums | Power BI scheduled refresh and Data Factory orchestration |
| Model training | Local deterministic churn training scripts | Azure Machine Learning |
| Model tracking | Local reports, manifests, lineage, and metadata | Azure ML jobs, MLflow, and Azure ML registry |
| Experiment metadata | Local versioned experiment catalogue and manifests | Azure ML/MLflow-style tracking or governed experiment tables |
| User segmentation | Local rule-based and KMeans segmentation | Azure Machine Learning |
| Recommendation baselines | Local popularity, segment-aware, and item-item CF baselines | Azure Machine Learning |
| Batch scoring | Local prediction CSV outputs | Azure ML batch endpoints |
| Batch segment assignment | Local assignment CSV outputs | Azure ML batch endpoints |
| Batch recommendation generation | Local recommendation CSV and reason JSONL outputs | Azure ML batch endpoints or Synapse scheduled jobs |
| Online scoring | Future scope only | Azure ML managed online endpoints |
| GenAI insights | Mocked or disabled by default | Azure AI Foundry and Azure OpenAI |
| Dashboards | Local documented outputs | Power BI |
| Observability | Quality reports and structured run metrics | Azure Monitor and Application Insights |
| Governance | Executable contracts and lineage manifests | Microsoft Purview |
| Secrets | Environment variable names only | Azure Key Vault references |
| Identity | Local developer identity | Microsoft Entra ID, managed identities, Azure RBAC |

## Design Principles

- Default validation must not require Azure credentials.
- Azure configuration examples must contain placeholders only.
- Domain logic should remain platform-neutral.
- Azure adapters should be added only when corresponding local behaviour is already tested.
- Infrastructure templates are planned, not active, in Milestone 6.
- No Azure service is deployed by the current repository.

The churn, segmentation, recommendation, experiment-analysis, product-insight, and reporting workflows map trusted accepted data and evidence to ADLS Gen2 trusted or curated zones, feature, interaction and metric preparation to Synapse or Azure ML data preparation, experiment tracking to Azure ML jobs and MLflow, prompt packages to Azure AI Foundry, optional future generation to Azure OpenAI, model registry to Azure ML registry, semantic reporting outputs to Power BI, monitoring to Azure Monitor and Azure ML monitoring, secrets to Key Vault, identity to managed identity and Azure RBAC, governance and lineage to Microsoft Purview, and dashboard consumption to Power BI. The local implementation does not install Azure SDKs, create clients, deploy resources, create `.pbix` files, or claim an Azure ML endpoint exists.
