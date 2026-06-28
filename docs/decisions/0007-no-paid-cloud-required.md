# ADR 0007: No Paid Cloud Resources Required for Default Validation

Status: Accepted

## Context

Default validation should be accessible to reviewers without subscriptions, credentials, or cloud spend.

## Decision

CI and local quality commands will not require Azure services. Azure deployment will remain optional until explicitly implemented.

## Consequences

Quality gates are fast and portable. Azure integration tests, when added, should be clearly separated and skipped by default without credentials.

## Alternatives Considered

Running CI against live Azure resources was rejected for cost, security, and reproducibility reasons.

