# Data Contracts

These are documentation-only contracts for planned synthetic datasets. No data is generated in Milestone 1.

## `users.csv`

Purpose: synthetic user profile and acquisition context.
Grain: one row per synthetic user.
Primary key: `user_id`.
Foreign keys: none.
Representative fields: `user_id`, `created_at`, `country`, `persona`, `acquisition_channel`, `device_preference`.
Time semantics: `created_at` is the user creation timestamp.
Validation: unique user IDs, valid timestamps, allowed acquisition values.
Sensitivity: synthetic low sensitivity.
Mode: batch.

## `sessions.jsonl`

Purpose: session-level product visits.
Grain: one record per session.
Primary key: `session_id`.
Foreign keys: `user_id`.
Representative fields: `session_id`, `user_id`, `session_started_at`, `session_ended_at`, `device_type`, `traffic_source`.
Time semantics: event time from session start and end.
Validation: known user, start before end, non-null session ID.
Sensitivity: synthetic behavioural.
Mode: batch and streaming.

## `clickstream_events.jsonl`

Purpose: event-level product behaviour.
Grain: one record per product event.
Primary key: `event_id`.
Foreign keys: `user_id`, `session_id`.
Representative fields: `event_id`, `user_id`, `session_id`, `event_timestamp`, `event_name`, `journey_stage`, `page`, `feature_name`.
Time semantics: event time from `event_timestamp`.
Validation: unique event ID, valid event name, known session, timestamp within session where applicable.
Sensitivity: synthetic behavioural.
Mode: streaming and batch replay.

## `feature_usage.csv`

Purpose: feature-level adoption and engagement facts.
Grain: one row per user, feature, and observation window.
Primary key: `user_id`, `feature_name`, `window_start`, `window_end`.
Foreign keys: `user_id`.
Representative fields: `feature_name`, `usage_count`, `first_used_at`, `last_used_at`, `is_adopted`.
Time semantics: observation window with derived first and last usage times.
Validation: non-negative usage, supported feature names, valid window bounds.
Sensitivity: synthetic behavioural.
Mode: batch.

## `subscriptions.csv`

Purpose: subscription status and plan history.
Grain: one row per user subscription state period.
Primary key: `subscription_id`.
Foreign keys: `user_id`.
Representative fields: `subscription_id`, `user_id`, `plan_name`, `status`, `effective_from`, `effective_to`, `monthly_recurring_revenue`.
Time semantics: effective-time intervals.
Validation: valid status, non-overlapping active periods per user, non-negative revenue.
Sensitivity: synthetic commercial.
Mode: batch.

## `experiment_assignments.csv`

Purpose: controlled experiment exposure and variant assignment.
Grain: one row per user per experiment.
Primary key: `experiment_id`, `user_id`.
Foreign keys: `user_id`.
Representative fields: `experiment_id`, `user_id`, `variant`, `assigned_at`, `eligible_at`, `exposure_event_id`.
Time semantics: assignment and exposure event time.
Validation: one variant per user per experiment, valid control/treatment labels, assignment before exposure.
Sensitivity: synthetic behavioural.
Mode: batch and streaming.

## `customer_feedback.csv`

Purpose: synthetic feedback text for theme and sentiment analysis.
Grain: one row per feedback item.
Primary key: `feedback_id`.
Foreign keys: optional `user_id`, optional `session_id`.
Representative fields: `feedback_id`, `user_id`, `submitted_at`, `channel`, `feedback_text`, `rating`, `product_area`.
Time semantics: submission event time.
Validation: non-empty text, valid rating range, supported channel values.
Sensitivity: synthetic text; future real deployments would require strict controls.
Mode: batch.

