# Governed Recommendation Baseline

Milestone 8 implements a deterministic, interpretable recommendation baseline over trusted Milestone 3 accepted data. The workflow is intended for offline product analysis and portfolio evidence, not online serving, causal treatment selection, uplift modelling, or automated user decisions.

## Scope

The baseline supports feature discovery, templates, automations, integrations, education, workflow guidance, and collaboration actions for synthetic NexaFlow users. It produces point-in-time interactions, candidate sets, ranked recommendations, reasons, offline ranking metrics, diagnostics, lineage, metadata, and a concise model card.

The implementation deliberately excludes online APIs, real-time feature stores, multi-armed bandits, reinforcement learning, deep learning recommenders, GenAI explanations, formal A/B inference, Azure SDK clients, and Power BI files.

## Data Boundary

Inputs must be trusted accepted outputs from the ingestion pipeline. The recommendation workflow loads the ingestion manifest, contract versions, accepted users, subscriptions, and clickstream events through the same trusted input conventions used by funnel, retention, churn, and segmentation workflows.

Each run has:

- a historical lookback window ending at the recommendation snapshot timestamp;
- a snapshot timestamp used for training interactions and candidate eligibility;
- a future holdout window used only for offline evaluation.

Post-snapshot interactions are not used for candidate generation, popularity scores, segment reconstruction, or item similarity. Future holdout interactions are used only to compute precision, recall, hit rate, MRR, MAP, and NDCG.

## Catalogue

The governed item catalogue has stable item IDs, names, categories, feature families, descriptions, eligibility constraints, prerequisite actions, incompatible prior actions, active flags, catalogue version, and synthetic-data markers.

Implemented categories:

- `feature`
- `template`
- `automation`
- `integration`
- `workflow`
- `education`
- `collaboration_action`

Candidate generation applies active status, plan eligibility, optional persona eligibility, optional company-size eligibility, prior consumption rules, prerequisites, and incompatible prior actions. Non-repeatable consumed items are withheld from future candidate sets.

## Interaction Mapping

The versioned interaction mapping converts allowed clickstream event names into implicit feedback strengths:

| Strength | Weight |
| --- | ---: |
| `exposure` | 0.10 |
| `view` | 0.25 |
| `click` | 0.50 |
| `trial` | 1.00 |
| `use` | 1.50 |
| `successful_use` | 2.00 |
| `repeat_use` | 3.00 |
| `acceptance` | 3.00 |

Mapped examples include recommendation exposure, clicks and accepts; template selection; automation creation and execution; integration connection; collaboration actions; onboarding completion; project creation; task usage; search; notification opening; and report export.

## Models

Four deterministic baselines are compared:

- global popularity over historical implicit interactions;
- recent popularity over the recent slice of the lookback window;
- segment-aware popularity using Milestone 7 rule-based segment reconstruction;
- item-item collaborative filtering with cosine similarity over user-item interaction scores.

Sparse segment or similarity scores fall back to popularity, with fallback rates reported in diagnostics and model metadata.

## Evaluation

Offline evaluation is descriptive. The workflow reports metrics by model and by top-K, including precision, recall, hit rate, MRR, MAP, NDCG, catalogue coverage, novelty, diversity, fallback rate, segment metrics, and cold-start metrics.

Model selection rejects models below coverage guardrails, prioritises NDCG@5, uses recall@5 as a tie-breaker, and prefers simpler baselines where quality is materially similar. The selected model is written to model metadata and the recommendation manifest.

## Outputs

Runtime outputs are written under `outputs/models/recommendations/<run_id>/` and are ignored by Git. Full runtime outputs include user-item interactions, candidate items, recommendations, reasons, model comparison, metrics, similarity, coverage, metadata, diagnostics, lineage, manifest, definition, catalogue, mapping, and model card.

Committed evidence under `docs/evidence/milestone-8/` is intentionally concise and excludes full interaction, candidate, recommendation, and reason files.

## Azure Mapping

The local workflow maps trusted data storage to ADLS Gen2, interaction preparation and batch feature preparation to Synapse or Azure ML data preparation, model training and batch generation to Azure ML jobs, experiment tracking to MLflow, batch output publication to ADLS Gen2 or Synapse, governance to Microsoft Purview, and monitoring to Azure Monitor. No Azure resources are deployed by this milestone.
