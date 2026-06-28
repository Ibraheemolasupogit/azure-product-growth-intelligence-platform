# Data Contracts

These contracts describe the synthetic NexaFlow datasets introduced in Milestone 2. The data is entirely synthetic and must not be treated as representative of a real customer population.

## `users.csv`

Purpose: synthetic user profile and acquisition context.
Grain: one row per synthetic user.
Primary key: `user_id`.
Foreign keys: none.
Representative fields: `user_id`, `signup_timestamp`, `country`, `region`, `acquisition_channel`, `device_preference`, `persona`, `company_size_band`, `initial_plan`, `marketing_consent`, `is_team_account`, `synthetic_record`.
Time semantics: `signup_timestamp` is the synthetic account creation time in UTC.
Validation: unique user IDs, valid signup timestamps, fictional categorical values, no unnecessary personal identifiers.
Sensitivity: synthetic low sensitivity.
Mode: batch.

## `sessions.jsonl`

Purpose: session-level product visits.
Grain: one record per user session.
Primary key: `session_id`.
Foreign keys: `user_id`.
Representative fields: `session_id`, `user_id`, `session_start_timestamp`, `session_end_timestamp`, `device_type`, `operating_system`, `traffic_source`, `country`, `event_count`, `session_duration_seconds`, `synthetic_record`.
Time semantics: session start and end timestamps are stored in UTC.
Validation: known user, start before end, event count reconciles to clickstream events.
Sensitivity: synthetic behavioural.
Mode: batch and streaming-compatible.

## `clickstream_events.jsonl`

Purpose: event-level product behaviour.
Grain: one record per product event.
Primary key: `event_id`.
Foreign keys: `user_id`, `session_id`.
Representative fields: `event_id`, `session_id`, `user_id`, `event_timestamp`, `event_name`, `feature_name`, `page_name`, `journey_stage`, `device_type`, `event_sequence_number`, `experiment_id`, `experiment_variant`, `recommendation_id`, `properties`, `synthetic_record`.
Time semantics: event time from `event_timestamp`, stored in UTC.
Validation: unique event ID, known user and session, timestamp inside session, increasing sequence numbers per session, taxonomy-compatible feature names.
Sensitivity: synthetic behavioural.
Mode: streaming and batch replay.

## `feature_usage.csv`

Purpose: deterministic feature-level usage derived from clickstream events.
Grain: one row per user, feature, and observation date with recorded activity.
Primary key: `usage_id`.
Foreign keys: `user_id`.
Representative fields: `usage_id`, `user_id`, `observation_date`, `feature_name`, `usage_count`, `active_minutes`, `successful_action_count`, `error_count`, `synthetic_record`.
Time semantics: observation date is derived from event timestamps.
Validation: non-negative counts and reconciliation to clickstream events.
Sensitivity: synthetic behavioural.
Mode: batch.

## `subscriptions.csv`

Purpose: subscription status and plan history.
Grain: one row per subscription history period.
Primary key: `subscription_id`.
Foreign keys: `user_id`.
Representative fields: `subscription_id`, `user_id`, `plan_name`, `billing_cycle`, `status`, `period_start_timestamp`, `period_end_timestamp`, `trial_start_timestamp`, `trial_end_timestamp`, `monthly_recurring_revenue`, `cancellation_reason`, `synthetic_record`.
Time semantics: effective-time intervals in UTC.
Validation: known user, valid plan, non-overlapping periods per user, non-negative recurring revenue.
Sensitivity: synthetic commercial.
Mode: batch.

## `experiment_assignments.csv`

Purpose: controlled experiment assignment and simulated exposure/conversion state.
Grain: one row per user and experiment assignment.
Primary key: `assignment_id`.
Foreign keys: `user_id`.
Representative fields: `assignment_id`, `experiment_id`, `user_id`, `variant`, `assignment_timestamp`, `eligibility_segment`, `exposure_timestamp`, `conversion_timestamp`, `converted`, `synthetic_record`.
Time semantics: assignment, exposure, and conversion timestamps are event-time values in UTC.
Validation: known user, valid experiment and variant, exposure after assignment, conversion after exposure, conversion flag agrees with timestamp presence.
Sensitivity: synthetic behavioural.
Mode: batch and streaming-compatible.

## `customer_feedback.csv`

Purpose: controlled synthetic feedback text for later theme and sentiment evaluation.
Grain: one row per feedback submission.
Primary key: `feedback_id`.
Foreign keys: `user_id`.
Representative fields: `feedback_id`, `user_id`, `feedback_timestamp`, `feedback_channel`, `rating`, `feedback_text`, `feedback_theme`, `feature_name`, `synthetic_sentiment_label`, `synthetic_record`.
Time semantics: submission timestamp in UTC.
Validation: known user, timestamp after signup, valid rating range, feedback text from controlled templates.
Sensitivity: synthetic text; not real customer feedback.
Mode: batch.

