# ADR 0006: Separate Descriptive Analytics, Predictive ML, and GenAI

Status: Accepted

## Context

Product analytics, predictive modelling, and GenAI insight generation have different reliability, validation, and governance needs.

## Decision

The codebase separates descriptive analytics, predictive ML, experimentation, recommendation, and GenAI modules.

## Consequences

Each workload can be tested with appropriate evidence. GenAI should consume grounded outputs rather than become a hidden source of metric logic.

## Alternatives Considered

Combining all intelligence workflows into one module was rejected because it would blur ownership and testing boundaries.

