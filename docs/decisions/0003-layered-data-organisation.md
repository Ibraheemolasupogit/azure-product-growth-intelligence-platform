# ADR 0003: Layered Data Organisation

Status: Accepted

## Context

Product analytics pipelines need clear separation between source-shaped data, validated data, derived features, and serving outputs.

## Decision

The repository uses raw, interim, processed, sample, output, and report zones. Future Azure storage should mirror these conceptual layers.

## Consequences

Data quality and lineage expectations are easier to explain. Generated data remains ignored by Git unless deliberately added as small documented samples.

## Alternatives Considered

A single flat data directory was rejected because it obscures validation and serving boundaries.

