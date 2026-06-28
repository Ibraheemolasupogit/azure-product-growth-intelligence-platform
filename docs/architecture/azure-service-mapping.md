# Azure Service Mapping

The platform is local-first, but each major component is designed to map cleanly to Azure services when optional deployment work is introduced.

| Capability | Local reference implementation | Azure-native implementation |
| --- | --- | --- |
| Product event ingestion | Local JSONL/CSV interfaces | Azure Event Hubs |
| Raw storage | `data/raw` | Azure Data Lake Storage Gen2 raw container |
| Curated storage | `data/processed` | Azure Data Lake Storage Gen2 curated container |
| Stream processing | Local replay or Python adapter | Azure Stream Analytics or Azure Functions |
| Analytical serving | Local output tables | Azure Synapse Analytics |
| Model training | Local deterministic training scripts | Azure Machine Learning |
| Model tracking | Local reports and metadata | Azure Machine Learning registry and jobs |
| GenAI insights | Mocked or disabled by default | Azure AI Foundry and Azure OpenAI |
| Dashboards | Local documented outputs | Power BI |
| Observability | Structured logs | Azure Monitor and Application Insights |
| Governance | Documentation and contracts | Microsoft Purview |
| Secrets | Environment variable names only | Azure Key Vault references |
| Identity | Local developer identity | Microsoft Entra ID, managed identities, Azure RBAC |

## Design Principles

- Default validation must not require Azure credentials.
- Azure configuration examples must contain placeholders only.
- Domain logic should remain platform-neutral.
- Azure adapters should be added only when corresponding local behaviour is already tested.
- Infrastructure templates are planned, not active, in Milestone 1.

