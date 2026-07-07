# GenAI Insight Governance

Milestone 10 uses deterministic local generation by default. The assistant is intentionally governed before any future live LLM adapter is introduced.

## Required Guardrails

- Every insight must cite at least one local evidence artifact.
- Numeric claims must be generated from parsed evidence.
- Synthetic-data disclaimers must appear in insights and reports.
- Unsupported causal language is blocked.
- Churn outputs must be described as risk indicators, not certainties.
- Recommendation outputs must be described as rankings, not probabilities.
- Segment names must be described as analytical interpretations.
- Experiment decisions must retain sample-size and guardrail caveats.

## Provider Policy

The implemented provider is `deterministic_template`. It performs no network calls and is suitable for CI. The `azure_openai_placeholder` provider is configuration metadata only. A future live provider would require Azure AI Content Safety review, prompt logging, managed identity or Key Vault secret handling, privacy review, monitoring, and human approval before product use.

## Review Expectations

Insight reports should be reviewed by product, data, and risk stakeholders. They are intended to prioritise investigation, not automate roadmap decisions. Evidence is synthetic and cannot be treated as external product truth.
