# Local-to-Azure Mapping

The repository keeps domain logic platform-neutral while documenting how each component could map to Azure.

| Local component | Local artifact | Azure mapping | Deployment status |
| --- | --- | --- | --- |
| Synthetic sources | `data/samples/nexaflow` | Synthetic source generator or controlled test data lake | Local only |
| Batch ingestion | `ingest-batch` CLI | Azure Data Factory plus ADLS Gen2 | Not deployed |
| Stream simulation | `ingest-stream` CLI | Event Hubs plus Functions or Stream Analytics | Not deployed |
| Quality reports | `docs/evidence/milestone-3` | Purview quality annotations and Monitor logs | Not deployed |
| Funnel analytics | `analyse-funnels` CLI | Synapse transformations | Not deployed |
| Retention analytics | `analyse-retention` CLI | Synapse transformations | Not deployed |
| Churn model | `train-churn-model` CLI | Azure ML training and batch scoring | Not deployed |
| Segmentation | `segment-users` CLI | Azure ML jobs | Not deployed |
| Recommendations | `build-recommendations` CLI | Azure ML or Synapse jobs | Not deployed |
| Experiment analysis | `analyse-experiments` CLI | Governed Python jobs or Azure ML | Not deployed |
| Product insights | `generate-product-insights` CLI | Azure AI Foundry / Azure OpenAI adapter | Not deployed |
| Reporting layer | `build-reporting-layer` CLI | Power BI semantic model and ADLS curated outputs | Not deployed |
| CI quality gates | `.github/workflows/ci.yml` | GitHub Actions | Active for validation only |

The mapping is intentionally descriptive. It does not create infrastructure or require credentials.
