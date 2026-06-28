# ADR 0001: Synthetic Data Only

Status: Accepted

## Context

The project is intended for public portfolio and reproducible technical review. Real customer data would create privacy, security, compliance, and licensing risks.

## Decision

Default datasets will be synthetic only. No real customer records, production telemetry, secrets, or proprietary exports should be committed.

## Consequences

The repository can be run and reviewed safely. Synthetic data must be realistic enough to demonstrate product analytics without implying real business performance.

## Alternatives Considered

Using anonymised production data was rejected because anonymisation can be fragile and unnecessary for the project objective.

