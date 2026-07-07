# Interview Explanation Guide

## Short Pitch

This is a local-first, Azure-mappable product growth intelligence platform. It demonstrates data generation, ingestion, validation, analytics, ML, experiments, deterministic product insights, and Power BI-ready reporting over synthetic data.

## How to Explain the Design

The repository separates source generation, data quality, analytics, ML, insight generation, reporting, and architecture documentation. Each milestone leaves deterministic evidence so a reviewer can inspect behavior without needing cloud access.

## Role Mapping

- Product analytics: funnel, retention, product health, reporting metrics.
- Growth/data science: churn, segmentation, recommendations, experiments.
- Analytics engineering: contracts, lineage, semantic model, evidence checks.
- Azure data/AI architecture: Event Hubs, ADLS Gen2, Synapse, Azure ML, AI Foundry, Power BI, Purview, Key Vault, Monitor.

## Honest Limitations

No live deployment exists. Synthetic data is useful for reproducible review but not a substitute for production scale, privacy review, security hardening, or model-risk validation.
