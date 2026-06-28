# ADR 0004: Configuration and Secret Management

Status: Accepted

## Context

The project must support local and Azure-like environments without committing secrets.

## Decision

Configuration is stored in safe YAML examples. Sensitive values are represented by environment variable names and future Key Vault references, not literal credentials.

## Consequences

Developers can inspect configuration safely. Future implementations need explicit secret resolution and validation.

## Alternatives Considered

Committing local `.env` files was rejected because it encourages accidental secret exposure.

