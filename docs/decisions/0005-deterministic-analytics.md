# ADR 0005: Deterministic and Reproducible Analytics

Status: Accepted

## Context

Synthetic generation, analytical outputs, and model training need stable behaviour for tests and review.

## Decision

The platform will use explicit random seeds, event-time semantics, versioned contracts, and deterministic local defaults.

## Consequences

Results should be reproducible across macOS, Linux, and GitHub Actions. Later milestones must test any stochastic behaviour.

## Alternatives Considered

Unseeded random generation was rejected because it makes test failures and portfolio review harder to diagnose.

