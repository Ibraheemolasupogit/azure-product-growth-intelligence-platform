"""Central NexaFlow synthetic data catalogues and event taxonomy."""

from dataclasses import dataclass
from typing import Any

PERSONAS = (
    "solo_professional",
    "small_team_member",
    "team_admin",
    "operations_lead",
    "casual_explorer",
    "power_user",
)

ACQUISITION_CHANNELS = (
    "organic_search",
    "paid_search",
    "content_marketing",
    "partner_referral",
    "product_led_referral",
    "app_marketplace",
)

COUNTRIES = ("United States", "United Kingdom", "Canada", "Australia", "Germany", "Netherlands")
REGIONS_BY_COUNTRY = {
    "United States": "North America",
    "Canada": "North America",
    "United Kingdom": "Europe",
    "Germany": "Europe",
    "Netherlands": "Europe",
    "Australia": "Asia Pacific",
}

DEVICE_TYPES = ("desktop", "mobile", "tablet")
OPERATING_SYSTEMS = ("macOS", "Windows", "iOS", "Android", "Linux")
TRAFFIC_SOURCES = ("direct", "search", "email", "referral", "paid", "marketplace")
COMPANY_SIZE_BANDS = ("solo", "2-10", "11-50", "51-200")

PLAN_CATALOGUE: dict[str, dict[str, Any]] = {
    "free": {"monthly_recurring_revenue": 0, "features": ("dashboard", "tasks", "search")},
    "starter": {
        "monthly_recurring_revenue": 12,
        "features": ("dashboard", "tasks", "search", "files", "comments", "notifications"),
    },
    "team": {
        "monthly_recurring_revenue": 29,
        "features": (
            "dashboard",
            "tasks",
            "search",
            "files",
            "comments",
            "notifications",
            "collaboration",
            "integrations",
        ),
    },
    "business": {
        "monthly_recurring_revenue": 79,
        "features": (
            "dashboard",
            "tasks",
            "search",
            "files",
            "comments",
            "notifications",
            "collaboration",
            "integrations",
            "automation",
            "reports",
        ),
    },
}

PERSONA_BEHAVIOUR: dict[str, dict[str, Any]] = {
    "solo_professional": {
        "company_size": "solo",
        "preferred_features": ("tasks", "dashboard", "search"),
        "sessions": (3, 7),
        "upgrade": 0.24,
        "churn": 0.16,
        "feedback": 0.18,
        "collaboration": 0.10,
    },
    "small_team_member": {
        "company_size": "2-10",
        "preferred_features": ("tasks", "comments", "files", "notifications"),
        "sessions": (4, 9),
        "upgrade": 0.30,
        "churn": 0.12,
        "feedback": 0.20,
        "collaboration": 0.40,
    },
    "team_admin": {
        "company_size": "11-50",
        "preferred_features": ("collaboration", "dashboard", "integrations", "reports"),
        "sessions": (6, 12),
        "upgrade": 0.56,
        "churn": 0.08,
        "feedback": 0.24,
        "collaboration": 0.72,
    },
    "operations_lead": {
        "company_size": "51-200",
        "preferred_features": ("automation", "integrations", "reports", "dashboard"),
        "sessions": (5, 11),
        "upgrade": 0.52,
        "churn": 0.10,
        "feedback": 0.22,
        "collaboration": 0.55,
    },
    "casual_explorer": {
        "company_size": "solo",
        "preferred_features": ("dashboard", "tasks", "templates"),
        "sessions": (1, 4),
        "upgrade": 0.08,
        "churn": 0.34,
        "feedback": 0.12,
        "collaboration": 0.05,
    },
    "power_user": {
        "company_size": "2-10",
        "preferred_features": ("automation", "tasks", "integrations", "search", "reports"),
        "sessions": (8, 15),
        "upgrade": 0.62,
        "churn": 0.06,
        "feedback": 0.28,
        "collaboration": 0.48,
    },
}


@dataclass(frozen=True)
class EventSpec:
    """Product event taxonomy entry."""

    event_name: str
    journey_stage: str
    feature_name: str | None
    event_type: str
    expected_properties: tuple[str, ...]


EVENT_TAXONOMY: dict[str, EventSpec] = {
    "account_created": EventSpec("account_created", "acquisition", None, "outcome", ("channel",)),
    "onboarding_started": EventSpec("onboarding_started", "onboarding", None, "action", ()),
    "onboarding_step_completed": EventSpec(
        "onboarding_step_completed", "onboarding", None, "success", ("step",)
    ),
    "onboarding_completed": EventSpec("onboarding_completed", "activation", None, "outcome", ()),
    "workspace_created": EventSpec("workspace_created", "activation", "workspace", "success", ()),
    "template_selected": EventSpec("template_selected", "activation", "templates", "action", ()),
    "session_started": EventSpec("session_started", "engagement", None, "exposure", ()),
    "dashboard_viewed": EventSpec("dashboard_viewed", "engagement", "dashboard", "action", ()),
    "project_created": EventSpec("project_created", "engagement", "projects", "success", ()),
    "task_created": EventSpec("task_created", "engagement", "tasks", "action", ()),
    "task_completed": EventSpec("task_completed", "engagement", "tasks", "success", ()),
    "file_uploaded": EventSpec("file_uploaded", "engagement", "files", "success", ()),
    "comment_added": EventSpec("comment_added", "engagement", "comments", "action", ()),
    "search_performed": EventSpec(
        "search_performed", "engagement", "search", "action", ("query_type",)
    ),
    "notification_opened": EventSpec(
        "notification_opened", "engagement", "notifications", "action", ()
    ),
    "invite_sent": EventSpec("invite_sent", "collaboration", "collaboration", "action", ()),
    "invite_accepted": EventSpec(
        "invite_accepted", "collaboration", "collaboration", "success", ()
    ),
    "member_added": EventSpec("member_added", "collaboration", "collaboration", "success", ()),
    "project_shared": EventSpec("project_shared", "collaboration", "collaboration", "success", ()),
    "automation_created": EventSpec("automation_created", "advanced", "automation", "action", ()),
    "automation_executed": EventSpec(
        "automation_executed", "advanced", "automation", "success", ()
    ),
    "integration_connected": EventSpec(
        "integration_connected", "advanced", "integrations", "success", ("integration_type",)
    ),
    "report_exported": EventSpec("report_exported", "advanced", "reports", "success", ()),
    "trial_started": EventSpec("trial_started", "monetisation", "billing", "outcome", ()),
    "upgrade_prompt_viewed": EventSpec(
        "upgrade_prompt_viewed", "monetisation", "billing", "exposure", ("prompt",)
    ),
    "subscription_started": EventSpec(
        "subscription_started", "monetisation", "billing", "outcome", ("plan_name",)
    ),
    "plan_upgraded": EventSpec(
        "plan_upgraded", "monetisation", "billing", "outcome", ("plan_name",)
    ),
    "plan_downgraded": EventSpec(
        "plan_downgraded", "monetisation", "billing", "outcome", ("plan_name",)
    ),
    "cancellation_started": EventSpec("cancellation_started", "retention", "billing", "action", ()),
    "subscription_cancelled": EventSpec(
        "subscription_cancelled", "retention", "billing", "outcome", ("reason",)
    ),
    "recommendation_shown": EventSpec(
        "recommendation_shown", "recommendation", "recommendations", "exposure", ("surface",)
    ),
    "recommendation_clicked": EventSpec(
        "recommendation_clicked", "recommendation", "recommendations", "action", ("surface",)
    ),
    "recommendation_accepted": EventSpec(
        "recommendation_accepted", "recommendation", "recommendations", "success", ("surface",)
    ),
    "feature_error": EventSpec("feature_error", "reliability", None, "failure", ("error_code",)),
    "request_failed": EventSpec("request_failed", "reliability", None, "failure", ("status_code",)),
}

EVENTS_BY_FEATURE = {
    "dashboard": ("dashboard_viewed",),
    "tasks": ("task_created", "task_completed"),
    "files": ("file_uploaded",),
    "comments": ("comment_added",),
    "search": ("search_performed",),
    "notifications": ("notification_opened",),
    "collaboration": ("invite_sent", "invite_accepted", "member_added", "project_shared"),
    "automation": ("automation_created", "automation_executed"),
    "integrations": ("integration_connected",),
    "reports": ("report_exported",),
    "templates": ("template_selected",),
}

EXPERIMENT_CATALOGUE: dict[str, dict[str, Any]] = {
    "exp_simplified_onboarding": {
        "variants": ("control", "simplified"),
        "eligibility": ("new_user",),
        "base_conversion_lift": {"control": 0.0, "simplified": 0.10},
    },
    "exp_template_recommendation": {
        "variants": ("control", "recommended_templates"),
        "eligibility": ("activated_user",),
        "base_conversion_lift": {"control": 0.0, "recommended_templates": 0.07},
    },
    "exp_trial_upgrade_prompt": {
        "variants": ("control", "contextual_prompt"),
        "eligibility": ("free_or_trial_user",),
        "base_conversion_lift": {"control": 0.0, "contextual_prompt": 0.12},
    },
    "exp_automation_discovery": {
        "variants": ("control", "guided_discovery"),
        "eligibility": ("advanced_feature_user",),
        "base_conversion_lift": {"control": 0.0, "guided_discovery": 0.08},
    },
}

FEEDBACK_TEMPLATES = {
    "positive": (
        "NexaFlow made it easier for our team to stay aligned on tasks.",
        "The automation setup saved time without needing extra training.",
        "The dashboard gives me a clear view of project progress.",
    ),
    "neutral": (
        "NexaFlow works for basic planning, but I still need more templates.",
        "The product is useful, although some notification settings are hard to tune.",
        "I can manage projects, but integrations would make the workflow smoother.",
    ),
    "negative": (
        "NexaFlow felt slow when uploading files during a busy project.",
        "The pricing was hard to justify for my small team.",
        "Too many notifications made collaboration harder to follow.",
    ),
}

FEEDBACK_THEMES = (
    "onboarding",
    "ease_of_use",
    "collaboration",
    "performance",
    "reliability",
    "pricing",
    "notifications",
    "integrations",
    "automation",
    "feature_requests",
)
