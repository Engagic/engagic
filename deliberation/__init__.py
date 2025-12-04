"""Deliberation module - citizen participation and opinion clustering

Core platform for civic deliberation on matters:
- Comment submission with trust-based moderation
- Vote aggregation (agree/disagree/pass)
- Opinion clustering via PCA + k-means
- Consensus detection across opinion groups
"""

from deliberation.clustering import compute_deliberation_clusters

__all__ = ["compute_deliberation_clusters"]
