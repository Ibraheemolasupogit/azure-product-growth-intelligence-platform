# Deployment Options

Milestone 12 documents deployment options without deploying anything. These options are deliberately non-executing and should be treated as architecture guidance.

## Option 1: Local Portfolio Review

Use the committed sample data and deterministic evidence. This is the default mode and requires no Azure subscription, credentials, or network access.

Recommended commands:

```bash
make quality
make verify-final-evidence
```

## Option 2: Azure-Mappable Pilot Design

Map local raw, interim, analytics, model, insight, and reporting outputs to ADLS Gen2 zones. Use Data Factory or Synapse pipelines for orchestration, Azure ML for model jobs, Microsoft Purview for lineage, and Power BI for reporting. This option still requires a separate secure implementation plan before deployment.

## Option 3: Production Program

A production program would add landing-zone controls, private networking, managed identity, Key Vault, Purview collections, Azure Monitor dashboards, Power BI workspace promotion, model-risk governance, cost budgets, incident response, and data-retention review.

## Explicitly Out of Scope

- No `az deployment` execution.
- No Terraform apply workflow.
- No service principals or tenant IDs.
- No hardcoded secrets.
- No live Azure OpenAI calls.
- No Power BI `.pbix` file.
- No Fabric workspace deployment.
