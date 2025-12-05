# Deliberation - Opinion Clustering & Consensus Detection

Clusters citizen opinions by voting patterns and detects consensus across opinion groups.

---

## Overview

The deliberation module provides the computational backend for civic deliberation on legislative matters. Given a vote matrix of participant opinions on comments, it clusters participants by voting patterns and identifies consensus items.

**Core Capabilities:**
- **PCA dimensionality reduction:** Projects voting patterns to 2D for visualization
- **K-means clustering:** Groups participants with similar voting patterns
- **Dynamic K selection:** Automatically determines optimal cluster count
- **Consensus detection:** Identifies comments with cross-group agreement via Laplace smoothing

---

## Structure

```
deliberation/
├── __init__.py      # 16 lines - Module exports, CONSENSUS_THRESHOLD constant
└── clustering.py    # 290 lines - PCA + k-means clustering algorithm

**Total:** 306 lines
```

---

## Algorithm

### Input

```python
vote_matrix: np.ndarray  # Shape: (n_participants, n_comments)
                         # Values: -1 (disagree), 0 (pass), 1 (agree), NaN (unvoted)
user_ids: List[str]      # User IDs corresponding to matrix rows
comment_ids: List[int]   # Comment IDs corresponding to matrix columns
```

### Processing Steps

1. **Impute missing votes:** Replace NaN with column averages (per-comment mean)
2. **PCA to 2D:** Project vote matrix to 2 dimensions for visualization
3. **Determine K:** `K = min(5, 2 + floor(n_participants / 12))`
4. **K-means clustering:** Group participants by voting patterns
5. **Compute consensus:** Laplace-smoothed agreement probability per cluster

### Dynamic K Formula

```
K = min(max_k, 2 + n_participants // 12)

Examples:
- 12 participants -> K = 3
- 24 participants -> K = 4
- 60+ participants -> K = 5 (capped)
```

### Consensus Score

Per-comment consensus = arithmetic mean of per-group agreement probabilities.

```
P(agree | cluster) = (agrees + 1) / (total + 2)  # Laplace smoothing
consensus = mean(P(agree) for each cluster)
```

- **High consensus (>0.8):** All groups tend to agree
- **Low consensus (<0.5):** Groups disagree on this comment

### Output

```python
{
    "positions": [[x, y], ...],           # 2D positions for each participant
    "clusters": {user_id: cluster_id},    # Cluster assignment per user
    "cluster_centers": [[x, y], ...],     # Centroid for each cluster
    "consensus": {comment_id: score},     # 0-1 score per comment
    "group_votes": {                      # Per-cluster vote tallies
        cluster_id: {
            comment_id: {"A": agrees, "D": disagrees, "S": seen}
        }
    },
    "k": int,                             # Number of clusters
    "n_participants": int,
    "n_comments": int
}
```

Returns `None` if insufficient data.

---

## Usage

```python
import numpy as np
from deliberation import compute_deliberation_clusters, CONSENSUS_THRESHOLD

# Build vote matrix (participants x comments)
# Values: 1 (agree), -1 (disagree), 0 (pass), np.nan (unvoted)
vote_matrix = np.array([
    [ 1,  1, -1, np.nan],
    [ 1,  1, -1, 0],
    [-1, -1,  1, 1],
    [-1, -1,  1, 1],
])

user_ids = ["user_a", "user_b", "user_c", "user_d"]
comment_ids = [101, 102, 103, 104]

results = compute_deliberation_clusters(vote_matrix, user_ids, comment_ids)

if results:
    # Find consensus comments
    consensus_comments = [
        cid for cid, score in results["consensus"].items()
        if score >= CONSENSUS_THRESHOLD
    ]

    # Get cluster assignments
    for user_id, cluster_id in results["clusters"].items():
        print(f"{user_id} -> Cluster {cluster_id}")

    # 2D positions for visualization
    positions = results["positions"]
```

---

## Edge Cases

| Condition | Behavior |
|-----------|----------|
| < 3 participants | Returns `None` (insufficient data) |
| < 2 comments | Returns `None` (insufficient data) |
| All identical votes | PCA returns zeros (can't separate participants) |
| All NaN in column | Imputes to 0.0 |
| Fewer participants than K | Adjusts K down to participant count |

---

## Constants

```python
CONSENSUS_THRESHOLD = 0.8  # Score above which a comment is considered consensus
```

---

## Related Modules

- **`database/repositories_async/deliberation.py`** (738 lines) - Persistence layer for deliberations, comments, votes, and cached clustering results
- **Database schema:** `deliberations`, `deliberation_comments`, `deliberation_votes`, `deliberation_results`, `deliberation_participants` tables

---

**Last Updated:** 2025-12-04
