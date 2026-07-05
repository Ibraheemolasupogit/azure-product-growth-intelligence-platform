# Recommendation Baseline Card

Intended use: offline product analysis and batch recommendation baseline review.
Out-of-scope use: online serving, automated decisions, uplift, or experiment winners.
All data is synthetic. Recommendations are ranked suggestions, not probabilities.

Snapshot: 2025-02-28T23:59:59Z. Lookback: 56 days.
Holdout: 28 days.
Models compared: global popularity, recent popularity, segment popularity,
and item-item CF.
Selected model: segment_popularity. NDCG@5: 0.400875.
Eligible users: 12.

Diversity, novelty and coverage are descriptive offline metrics. Item similarity is
associative and not causal. Production use would require online experimentation,
monitoring, privacy review and human oversight.

Azure mapping: trusted data in ADLS Gen2, interaction preparation in Synapse,
training and batch generation in Azure ML, tracking with MLflow,
governance via Purview.
