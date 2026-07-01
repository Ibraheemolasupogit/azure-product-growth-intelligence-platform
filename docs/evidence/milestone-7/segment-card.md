# User Segmentation Segment Card

Intended use: descriptive product, growth and customer-success analysis.
Out-of-scope use: automated adverse decisions, recommendations, uplift, or real-time serving.
All data is synthetic. Segment names are analytical interpretations, not causal claims.

Snapshot: 2025-03-31T23:59:59Z. Lookback days: 56.
Eligible snapshots: 12.
Methods: deterministic rule-based segmentation and KMeans clustering.
Preprocessing: numeric and binary features only, constant features removed, StandardScaler.
Cluster-count selection rejects undersized clusters, prioritises silhouette, uses stability as a tie-breaker and prefers simpler solutions.
Selected clusters: 2.
Stability: {'mean_adjusted_rand_score': 0.776547}.

## Segment Names
- cluster_01: collaboration_focused_teams
- cluster_02: inactive_or_declining_users

## Limitations

- Small sample evidence is illustrative.
- Clusters do not prove causal behaviour.
- Segment names require domain review before operational use.
- Monitor drift, profile suppression and assignment stability before production use.

Azure mapping: trusted data in ADLS Gen2, feature preparation in Synapse or Azure ML, clustering in Azure ML, tracking through MLflow, governance through Purview, and monitoring through Azure Monitor. No Azure resources are deployed here.
