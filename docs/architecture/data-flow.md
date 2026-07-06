# Data Flow

This document describes the logical data flow. Milestone 3 implements the local raw-to-interim ingestion and validation portion. Milestone 4 implements governed funnel analytics over trusted interim data. Milestone 5 implements governed retention and cohort analytics. Milestone 6 implements local leakage-aware churn prediction. Milestone 7 implements governed user segmentation. Milestone 8 implements governed recommendation baselines. Milestone 9 implements governed fixed-window experiment analysis. GenAI, dashboarding, and Azure deployment remain planned.

```mermaid
sequenceDiagram
    participant Source as Synthetic Sources
    participant Ingest as Ingestion
    participant Raw as Raw Layer
    participant Validate as Validation
    participant Curated as Curated Layer
    participant Analytics as Analytics and Features
    participant ML as ML and Experiments
    participant GenAI as GenAI Insights
    participant Serving as Serving Outputs
    participant Gov as Monitoring and Governance

    Source->>Ingest: Product events and batch records
    Ingest->>Raw: Append immutable source-shaped data
    Raw->>Validate: Apply contracts and quality rules
    Validate->>Curated: Publish valid behavioural data
    Validate->>Raw: Quarantine invalid records
    Curated->>Analytics: Build product metrics and features
    Analytics->>ML: Provide model and experiment inputs
    ML->>GenAI: Provide grounded summaries and evidence
    GenAI->>Serving: Publish reviewed insight artifacts
    Serving->>Gov: Emit lineage, quality, and monitoring signals
```

## Batch and Streaming Boundaries

Batch processing is suitable for source snapshots, subscriptions, experiment assignments, feedback extracts, historical metric recomputation, and model training datasets.

Streaming processing is suitable for clickstream events, session activity, feature usage, funnel progression, and low-latency monitoring. The same conceptual event contracts should support both paths.

## Validation and Quarantine

Invalid records are separated from accepted interim datasets with source location, failed rule IDs, diagnostics, and ingestion metadata. Milestone 3 implements schema checks, required fields, timestamp constraints, referential integrity, duplicate handling, allowed value rules, quality reports, lineage, and ingestion manifests.

## Serving Outputs

Serving outputs should be stable, documented tables that can be consumed by Power BI, notebooks, or downstream product reviews. The repository should avoid conflicting definitions of the same metric across files.

Milestone 4 writes funnel outputs under `outputs/analytics/funnels/<analysis_run_id>/`, including attempts, summary, stage metrics, segment metrics, time metrics, drop-off diagnostics, lineage, manifest, and diagnostics.

Milestone 5 writes retention outputs under `outputs/analytics/retention/<analysis_run_id>/`, including cohort memberships, user-period activity, retention matrices, long-format metrics, lifecycle status, resurrection analysis, lineage, manifest, and diagnostics.

Milestone 6 writes churn-model outputs under `outputs/models/churn/<model_run_id>/`, including churn definition, feature catalogue, snapshot labels, feature matrix, chronological splits, training and evaluation metrics, threshold analysis, predictions, feature importance, model metadata, model card, diagnostics, manifest, and lineage.

Milestone 7 writes segmentation outputs under `outputs/models/segmentation/<segmentation_run_id>/`, including segmentation definition, feature catalogue, snapshots, feature matrix, rule-based assignments, cluster candidate metrics, stability, assignments, profiles, centroids, PCA outputs, segment names, metadata, diagnostics, manifest, lineage, and segment card.

Milestone 8 writes recommendation outputs under `outputs/models/recommendations/<recommendation_run_id>/`, including recommendation definition, item catalogue, interaction mapping, point-in-time user-item interactions, candidate items, model comparison, offline metrics, metrics by K, segment metrics, cold-start metrics, item similarity, recommendations, deterministic reasons, catalogue coverage, metadata, diagnostics, manifest, lineage, and recommendation card.

Milestone 9 writes experiment-analysis outputs under `outputs/experiments/<analysis_run_id>/`, including experiment catalogue, populations, assignment integrity, sample-ratio mismatch, metric results, guardrails, segment effects, multiple-testing results, power analysis, decisions, summary, diagnostics, manifest, lineage, and reports.

```mermaid
flowchart LR
    A[Trusted accepted data] --> B[Point-in-time snapshots]
    B --> C[Lookback feature window]
    B --> D[Future label window]
    C --> E[Feature matrix]
    D --> F[Behavioural churn labels]
    E --> G[Chronological train validation test]
    F --> G
    G --> H[Baseline logistic and tree models]
    H --> I[Validation selection]
    I --> J[Held-out test evaluation]
    J --> K[Model card manifest lineage]
```

```mermaid
flowchart LR
    A[Trusted accepted data] --> B[Segmentation snapshot]
    B --> C[Historical lookback features]
    C --> D[Rule-based segments]
    C --> E[KMeans candidates]
    E --> F[Quality and stability selection]
    F --> G[Canonical clusters]
    G --> H[Profiles and segment names]
    G --> I[PCA coordinates]
    H --> J[Segment card manifest lineage]
    I --> J
```

```mermaid
flowchart LR
    A[Trusted accepted data] --> B[Experiment catalogue]
    B --> C[Assignment integrity]
    A --> C
    C --> D[Exposure derivation]
    D --> E[ITT and exposed populations]
    E --> F[Outcome attribution]
    F --> G[Treatment effects and guardrails]
    C --> H[Sample ratio mismatch]
    G --> I[Multiple testing and power]
    H --> J[Decision summary]
    I --> J
    J --> K[Experiment reports manifest lineage]
```

```mermaid
flowchart LR
    A[Trusted accepted data] --> B[Recommendation snapshot]
    B --> C[Historical interactions]
    B --> D[Catalogue eligibility]
    C --> E[Popularity and similarity baselines]
    D --> F[Candidate generation]
    F --> G[Ranked recommendations]
    E --> G
    B --> H[Future holdout window]
    G --> I[Offline ranking metrics]
    H --> I
    I --> J[Manifest card lineage]
```
