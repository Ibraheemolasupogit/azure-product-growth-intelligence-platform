"""Provider abstractions for product insight generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from product_growth_intelligence.data_generation.models import Record


class InsightProviderAdapter(Protocol):
    """Insight provider protocol."""

    @property
    def provider_id(self) -> str:
        """Provider identifier."""

    def build_prompt_package(self, inputs: Record) -> Record:
        """Build an auditable prompt package."""


@dataclass(frozen=True)
class DeterministicTemplateProvider:
    """Offline deterministic template provider used by default."""

    provider_id: str = "deterministic_template"

    def build_prompt_package(self, inputs: Record) -> Record:
        """Build a deterministic prompt package without calling an LLM."""

        return {
            "provider": self.provider_id,
            "generation_mode": "deterministic_template",
            "system_instruction": (
                "Generate only evidence-grounded product insights. Cite local artifacts, "
                "include synthetic-data caveats, and avoid unsupported causal claims."
            ),
            "input_sections": sorted(inputs),
            "llm_call_performed": False,
            "temperature": 0,
        }


@dataclass(frozen=True)
class AzureOpenAIPlaceholderProvider:
    """Configuration-only Azure OpenAI provider placeholder."""

    provider_id: str = "azure_openai_placeholder"
    endpoint_env_var: str = "AZURE_OPENAI_ENDPOINT"
    deployment_env_var: str = "AZURE_OPENAI_DEPLOYMENT"

    def build_prompt_package(self, inputs: Record) -> Record:
        """Build placeholder metadata without network calls."""

        return {
            "provider": self.provider_id,
            "generation_mode": "azure_openai_placeholder_no_call",
            "system_instruction": (
                "Future Azure OpenAI adapter must preserve grounding, safety checks, "
                "prompt logging, and content safety review before live use."
            ),
            "input_sections": sorted(inputs),
            "endpoint_env_var": self.endpoint_env_var,
            "deployment_env_var": self.deployment_env_var,
            "identity_pattern": "managed_identity_or_key_vault_future_pattern",
            "llm_call_performed": False,
        }


def provider_for(provider_id: str) -> InsightProviderAdapter:
    """Return the configured provider adapter."""

    if provider_id == "deterministic_template":
        return DeterministicTemplateProvider()
    if provider_id == "azure_openai_placeholder":
        return AzureOpenAIPlaceholderProvider()
    msg = f"Unsupported insight provider: {provider_id}."
    raise ValueError(msg)
