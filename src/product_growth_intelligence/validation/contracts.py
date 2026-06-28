"""Executable, versioned ingestion contracts for NexaFlow datasets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from product_growth_intelligence.data_generation.catalogues import (
    ACQUISITION_CHANNELS,
    COMPANY_SIZE_BANDS,
    COUNTRIES,
    DEVICE_TYPES,
    EVENT_TAXONOMY,
    EXPERIMENT_CATALOGUE,
    FEEDBACK_THEMES,
    OPERATING_SYSTEMS,
    PERSONAS,
    PLAN_CATALOGUE,
    TRAFFIC_SOURCES,
)
from product_growth_intelligence.data_generation.writers import CSV_COLUMNS, JSONL_COLUMNS

CONTRACT_VERSION = "2026-06-milestone-3"
SUPPORTED_SOURCE_CONTRACTS = frozenset({"2026-06-milestone-2", CONTRACT_VERSION})

FieldType = Literal["string", "boolean", "integer", "decimal", "date", "timestamp", "object"]
DatasetFormat = Literal["csv", "jsonl"]
Sensitivity = Literal["synthetic_low", "synthetic_feedback_text"]


@dataclass(frozen=True)
class FieldContract:
    """Field-level contract definition."""

    name: str
    field_type: FieldType
    nullable: bool = False
    allowed_values: frozenset[str] | None = None
    minimum: int | float | None = None
    maximum: int | float | None = None
    identifier_prefix: str | None = None


@dataclass(frozen=True)
class ForeignKey:
    """Foreign-key relationship to another ingestion dataset."""

    field_name: str
    target_dataset: str
    target_field: str


@dataclass(frozen=True)
class DatasetContract:
    """Executable dataset contract used by ingestion validation."""

    dataset: str
    filename: str
    file_format: DatasetFormat
    record_grain: str
    fields: tuple[FieldContract, ...]
    primary_key: str
    foreign_keys: tuple[ForeignKey, ...] = ()
    timestamp_fields: tuple[str, ...] = ()
    sensitivity: Sensitivity = "synthetic_low"
    schema_evolution: str = "additive optional fields require governance review"

    @property
    def required_fields(self) -> tuple[str, ...]:
        """Return required fields in stable order."""

        return tuple(field.name for field in self.fields if not field.nullable)

    @property
    def optional_fields(self) -> tuple[str, ...]:
        """Return nullable fields in stable order."""

        return tuple(field.name for field in self.fields if field.nullable)

    @property
    def field_names(self) -> tuple[str, ...]:
        """Return all expected fields in stable order."""

        return tuple(field.name for field in self.fields)

    def field_by_name(self) -> dict[str, FieldContract]:
        """Return field contracts keyed by field name."""

        return {field.name: field for field in self.fields}


def _allowed(values: tuple[str, ...] | list[str]) -> frozenset[str]:
    return frozenset(values)


CONTRACTS: dict[str, DatasetContract] = {
    "users": DatasetContract(
        dataset="users",
        filename="users.csv",
        file_format="csv",
        record_grain="one synthetic product account",
        primary_key="user_id",
        timestamp_fields=("signup_timestamp",),
        fields=(
            FieldContract("user_id", "string", identifier_prefix="syn_usr_"),
            FieldContract("signup_timestamp", "timestamp"),
            FieldContract("country", "string", allowed_values=_allowed(COUNTRIES)),
            FieldContract("region", "string"),
            FieldContract(
                "acquisition_channel", "string", allowed_values=_allowed(ACQUISITION_CHANNELS)
            ),
            FieldContract("device_preference", "string", allowed_values=_allowed(DEVICE_TYPES)),
            FieldContract("persona", "string", allowed_values=_allowed(PERSONAS)),
            FieldContract(
                "company_size_band", "string", allowed_values=_allowed(COMPANY_SIZE_BANDS)
            ),
            FieldContract("initial_plan", "string", allowed_values=frozenset(PLAN_CATALOGUE)),
            FieldContract("marketing_consent", "boolean"),
            FieldContract("is_team_account", "boolean"),
            FieldContract("synthetic_record", "boolean"),
        ),
    ),
    "sessions": DatasetContract(
        dataset="sessions",
        filename="sessions.jsonl",
        file_format="jsonl",
        record_grain="one user session summary",
        primary_key="session_id",
        foreign_keys=(ForeignKey("user_id", "users", "user_id"),),
        timestamp_fields=("session_start_timestamp", "session_end_timestamp"),
        fields=(
            FieldContract("session_id", "string", identifier_prefix="syn_ses_"),
            FieldContract("user_id", "string", identifier_prefix="syn_usr_"),
            FieldContract("session_start_timestamp", "timestamp"),
            FieldContract("session_end_timestamp", "timestamp"),
            FieldContract("device_type", "string", allowed_values=_allowed(DEVICE_TYPES)),
            FieldContract("operating_system", "string", allowed_values=_allowed(OPERATING_SYSTEMS)),
            FieldContract("traffic_source", "string", allowed_values=_allowed(TRAFFIC_SOURCES)),
            FieldContract("country", "string", allowed_values=_allowed(COUNTRIES)),
            FieldContract("event_count", "integer", minimum=0),
            FieldContract("session_duration_seconds", "integer", minimum=0),
            FieldContract("synthetic_record", "boolean"),
        ),
    ),
    "clickstream_events": DatasetContract(
        dataset="clickstream_events",
        filename="clickstream_events.jsonl",
        file_format="jsonl",
        record_grain="one product event",
        primary_key="event_id",
        foreign_keys=(
            ForeignKey("user_id", "users", "user_id"),
            ForeignKey("session_id", "sessions", "session_id"),
        ),
        timestamp_fields=("event_timestamp",),
        fields=(
            FieldContract("event_id", "string", identifier_prefix="syn_evt_"),
            FieldContract("session_id", "string", identifier_prefix="syn_ses_"),
            FieldContract("user_id", "string", identifier_prefix="syn_usr_"),
            FieldContract("event_timestamp", "timestamp"),
            FieldContract("event_name", "string", allowed_values=frozenset(EVENT_TAXONOMY)),
            FieldContract("feature_name", "string", nullable=True),
            FieldContract("page_name", "string"),
            FieldContract("journey_stage", "string"),
            FieldContract("device_type", "string", allowed_values=_allowed(DEVICE_TYPES)),
            FieldContract("event_sequence_number", "integer", minimum=1),
            FieldContract("experiment_id", "string", nullable=True),
            FieldContract("experiment_variant", "string", nullable=True),
            FieldContract("recommendation_id", "string", nullable=True),
            FieldContract("properties", "object"),
            FieldContract("synthetic_record", "boolean"),
        ),
    ),
    "feature_usage": DatasetContract(
        dataset="feature_usage",
        filename="feature_usage.csv",
        file_format="csv",
        record_grain="one user-feature-day aggregate",
        primary_key="usage_id",
        foreign_keys=(ForeignKey("user_id", "users", "user_id"),),
        fields=(
            FieldContract("usage_id", "string", identifier_prefix="syn_usg_"),
            FieldContract("user_id", "string", identifier_prefix="syn_usr_"),
            FieldContract("observation_date", "date"),
            FieldContract("feature_name", "string"),
            FieldContract("usage_count", "integer", minimum=0),
            FieldContract("active_minutes", "integer", minimum=0),
            FieldContract("successful_action_count", "integer", minimum=0),
            FieldContract("error_count", "integer", minimum=0),
            FieldContract("synthetic_record", "boolean"),
        ),
    ),
    "subscriptions": DatasetContract(
        dataset="subscriptions",
        filename="subscriptions.csv",
        file_format="csv",
        record_grain="one subscription state period",
        primary_key="subscription_id",
        foreign_keys=(ForeignKey("user_id", "users", "user_id"),),
        timestamp_fields=(
            "period_start_timestamp",
            "period_end_timestamp",
            "trial_start_timestamp",
            "trial_end_timestamp",
        ),
        fields=(
            FieldContract("subscription_id", "string", identifier_prefix="syn_sub_"),
            FieldContract("user_id", "string", identifier_prefix="syn_usr_"),
            FieldContract("plan_name", "string", allowed_values=frozenset(PLAN_CATALOGUE)),
            FieldContract("billing_cycle", "string", allowed_values=frozenset({"none", "monthly"})),
            FieldContract(
                "status",
                "string",
                allowed_values=frozenset({"active", "converted", "trial", "cancelled"}),
            ),
            FieldContract("period_start_timestamp", "timestamp"),
            FieldContract("period_end_timestamp", "timestamp", nullable=True),
            FieldContract("trial_start_timestamp", "timestamp", nullable=True),
            FieldContract("trial_end_timestamp", "timestamp", nullable=True),
            FieldContract("monthly_recurring_revenue", "decimal", minimum=0),
            FieldContract("cancellation_reason", "string", nullable=True),
            FieldContract("synthetic_record", "boolean"),
        ),
    ),
    "experiment_assignments": DatasetContract(
        dataset="experiment_assignments",
        filename="experiment_assignments.csv",
        file_format="csv",
        record_grain="one user experiment assignment",
        primary_key="assignment_id",
        foreign_keys=(ForeignKey("user_id", "users", "user_id"),),
        timestamp_fields=(
            "assignment_timestamp",
            "exposure_timestamp",
            "conversion_timestamp",
        ),
        fields=(
            FieldContract("assignment_id", "string", identifier_prefix="syn_asg_"),
            FieldContract(
                "experiment_id", "string", allowed_values=frozenset(EXPERIMENT_CATALOGUE)
            ),
            FieldContract("user_id", "string", identifier_prefix="syn_usr_"),
            FieldContract("variant", "string"),
            FieldContract("assignment_timestamp", "timestamp"),
            FieldContract("eligibility_segment", "string"),
            FieldContract("exposure_timestamp", "timestamp"),
            FieldContract("conversion_timestamp", "timestamp", nullable=True),
            FieldContract("converted", "boolean"),
            FieldContract("synthetic_record", "boolean"),
        ),
    ),
    "customer_feedback": DatasetContract(
        dataset="customer_feedback",
        filename="customer_feedback.csv",
        file_format="csv",
        record_grain="one synthetic feedback submission",
        primary_key="feedback_id",
        foreign_keys=(ForeignKey("user_id", "users", "user_id"),),
        timestamp_fields=("feedback_timestamp",),
        sensitivity="synthetic_feedback_text",
        fields=(
            FieldContract("feedback_id", "string", identifier_prefix="syn_fbk_"),
            FieldContract("user_id", "string", identifier_prefix="syn_usr_"),
            FieldContract("feedback_timestamp", "timestamp"),
            FieldContract(
                "feedback_channel",
                "string",
                allowed_values=frozenset({"in_app", "email", "support_ticket", "survey"}),
            ),
            FieldContract("rating", "integer", minimum=1, maximum=5),
            FieldContract("feedback_text", "string"),
            FieldContract("feedback_theme", "string", allowed_values=_allowed(FEEDBACK_THEMES)),
            FieldContract("feature_name", "string"),
            FieldContract(
                "synthetic_sentiment_label",
                "string",
                allowed_values=frozenset({"positive", "neutral", "negative"}),
            ),
            FieldContract("synthetic_record", "boolean"),
        ),
    ),
}


def contract_for_dataset(dataset: str) -> DatasetContract:
    """Return the executable contract for a dataset."""

    return CONTRACTS[dataset]


def contracts_by_filename() -> dict[str, DatasetContract]:
    """Return contracts keyed by expected filename."""

    return {contract.filename: contract for contract in CONTRACTS.values()}


def writer_columns_for(contract: DatasetContract) -> tuple[str, ...]:
    """Return Milestone 2 writer columns for contract-divergence tests."""

    if contract.file_format == "csv":
        return CSV_COLUMNS[contract.filename]
    return JSONL_COLUMNS[contract.filename]
