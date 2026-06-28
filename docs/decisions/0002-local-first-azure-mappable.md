# ADR 0002: Local-First and Azure-Mappable Architecture

Status: Accepted

## Context

Reviewers should be able to run default checks without cloud access, but the platform should still demonstrate Azure architecture judgement.

## Decision

Domain logic will run locally by default and map to Azure services through configuration, documentation, and future adapters.

## Consequences

The project remains reproducible and cost-free while preserving a credible path to Azure-native deployment.

## Alternatives Considered

Requiring Azure resources from the first milestone was rejected because it would reduce reproducibility and increase review friction.

