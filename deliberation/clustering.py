"""Deliberation clustering algorithm

Clusters participants by their voting patterns on comments.
Uses PCA for dimensionality reduction and k-means for clustering.

Algorithm:
1. Build vote matrix (participants x comments)
2. Impute missing votes with column averages
3. PCA to 2D for visualization
4. K-means clustering with dynamic K selection
5. Calculate consensus scores per comment

Confidence: 9/10 - well-understood algorithms with clear parameters.
"""

from typing import Any, Dict, List, Optional

import numpy as np
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans

from config import get_logger

logger = get_logger(__name__).bind(component="deliberation_clustering")


def compute_deliberation_clusters(
    vote_matrix: np.ndarray,
    user_ids: List[str],
    comment_ids: List[int],
) -> Optional[Dict[str, Any]]:
    """Compute opinion clusters from vote data.

    Args:
        vote_matrix: Shape (n_participants, n_comments).
                     Values: -1 (disagree), 0 (pass), 1 (agree), NaN (unvoted)
        user_ids: List of user IDs corresponding to matrix rows
        comment_ids: List of comment IDs corresponding to matrix columns

    Returns:
        Dict with clustering results:
            - positions: [[x, y], ...] for each participant
            - clusters: {user_id: cluster_id}
            - cluster_centers: [[x, y], ...] for each cluster
            - consensus: {comment_id: score} where score in [0, 1]
            - group_votes: {cluster_id: {comment_id: {A, D, S}}}
            - k: number of clusters
            - n_participants: number of participants
            - n_comments: number of comments
        Returns None if insufficient data for clustering.
    """
    n_participants, n_comments = vote_matrix.shape

    # Edge case: insufficient data
    if n_participants < 3:
        logger.debug("insufficient participants for clustering", n=n_participants)
        return None

    if n_comments < 2:
        logger.debug("insufficient comments for clustering", n=n_comments)
        return None

    # 1. Impute missing votes with column averages
    matrix = _impute_missing_votes(vote_matrix)

    # 2. PCA to 2D for visualization
    positions = _compute_pca(matrix)

    # 3. Determine K: min(5, 2 + floor(n/12))
    k = _determine_k(n_participants)

    # 4. K-means clustering
    cluster_labels = _compute_kmeans(matrix, k)

    # 5. Calculate consensus and group votes
    consensus, group_votes = _compute_consensus(
        matrix, cluster_labels, comment_ids, k
    )

    # 6. Compute cluster centers in 2D space
    cluster_centers = _compute_cluster_centers(positions, cluster_labels, k)

    logger.info(
        "computed deliberation clusters",
        n_participants=n_participants,
        n_comments=n_comments,
        k=k,
    )

    return {
        "positions": positions.tolist(),
        "clusters": {uid: int(cluster_labels[i]) for i, uid in enumerate(user_ids)},
        "cluster_centers": cluster_centers.tolist(),
        "consensus": {int(cid): float(score) for cid, score in consensus.items()},
        "group_votes": {
            int(gid): {int(cid): votes for cid, votes in gv.items()}
            for gid, gv in group_votes.items()
        },
        "k": k,
        "n_participants": n_participants,
        "n_comments": n_comments,
    }


def _impute_missing_votes(matrix: np.ndarray) -> np.ndarray:
    """Impute missing votes (NaN) with column averages.

    Uses per-comment average vote as imputation.
    Preserves variance while filling gaps from incomplete participation.

    Args:
        matrix: Vote matrix with NaN for missing votes

    Returns:
        Matrix with NaN replaced by column averages
    """
    # Calculate column means, ignoring NaN
    col_means = np.nanmean(matrix, axis=0)

    # Replace NaN in column means with 0 (for comments with no votes)
    col_means = np.nan_to_num(col_means, nan=0.0)

    # Create copy and replace NaN with column means
    result = matrix.copy()
    nan_mask = np.isnan(result)

    # Broadcast column means to NaN positions
    for j in range(result.shape[1]):
        result[nan_mask[:, j], j] = col_means[j]

    return result


def _compute_pca(matrix: np.ndarray) -> np.ndarray:
    """Project vote matrix to 2D using PCA.

    Args:
        matrix: Imputed vote matrix (n_participants, n_comments)

    Returns:
        2D positions (n_participants, 2)
    """
    # Handle edge case: fewer than 2 features
    if matrix.shape[1] < 2:
        # Return zeros - can't do meaningful PCA
        return np.zeros((matrix.shape[0], 2))

    # Handle edge case: all identical rows
    if np.allclose(matrix, matrix[0]):
        # All participants voted identically - can't separate them
        return np.zeros((matrix.shape[0], 2))

    pca = PCA(n_components=min(2, matrix.shape[1]))
    positions = pca.fit_transform(matrix)

    # Pad to 2D if only 1 component
    if positions.shape[1] == 1:
        positions = np.hstack([positions, np.zeros((positions.shape[0], 1))])

    return positions


def _determine_k(n_participants: int, max_k: int = 5) -> int:
    """Determine optimal number of clusters.

    Formula: K = min(max_k, 2 + floor(n/12))

    Examples:
        - 12 participants -> K = 3
        - 24 participants -> K = 4
        - 60+ participants -> K = 5 (capped)

    Args:
        n_participants: Number of participants
        max_k: Maximum number of clusters (default: 5)

    Returns:
        Number of clusters to use
    """
    k = 2 + n_participants // 12
    k = max(2, min(k, max_k, n_participants))
    return k


def _compute_kmeans(matrix: np.ndarray, k: int) -> np.ndarray:
    """Run k-means clustering on vote matrix.

    Args:
        matrix: Imputed vote matrix
        k: Number of clusters

    Returns:
        Cluster labels (0 to k-1) for each participant
    """
    # Handle edge case: fewer participants than clusters
    if matrix.shape[0] < k:
        k = matrix.shape[0]

    kmeans = KMeans(
        n_clusters=k,
        n_init=10,        # Number of random initializations
        max_iter=100,     # Max iterations per run
        random_state=42,  # Reproducibility
    )

    return kmeans.fit_predict(matrix)


def _compute_consensus(
    matrix: np.ndarray,
    cluster_labels: np.ndarray,
    comment_ids: List[int],
    k: int,
) -> tuple[Dict[int, float], Dict[int, Dict[int, Dict[str, int]]]]:
    """Calculate consensus scores and per-group vote tallies.

    Consensus = arithmetic mean of per-group agreement probabilities.
    Uses Laplace smoothing: P(agree) = (A + 1) / (S + 2)

    High consensus (>0.8) means all groups tend to agree.
    Low consensus (<0.5) means groups disagree on this comment.

    Args:
        matrix: Imputed vote matrix
        cluster_labels: Cluster assignment for each participant
        comment_ids: List of comment IDs
        k: Number of clusters

    Returns:
        Tuple of:
            - consensus: {comment_id: score} where score in [0, 1]
            - group_votes: {cluster_id: {comment_id: {A: agrees, D: disagrees, S: seen}}}
    """
    consensus = {}
    group_votes = {i: {} for i in range(k)}

    for j, cid in enumerate(comment_ids):
        probs = []

        for cluster_id in range(k):
            # Get votes from this cluster on this comment
            mask = cluster_labels == cluster_id
            votes_in_group = matrix[mask, j]

            # Count agrees, disagrees, total
            agrees = int(np.sum(votes_in_group == 1))
            disagrees = int(np.sum(votes_in_group == -1))
            total = len(votes_in_group)

            group_votes[cluster_id][cid] = {
                "A": agrees,
                "D": disagrees,
                "S": total,
            }

            # Laplace-smoothed probability of agreement
            # P(agree) = (A + 1) / (S + 2)
            p_agree = (agrees + 1) / (total + 2)
            probs.append(p_agree)

        # Consensus = arithmetic mean of per-group probabilities
        consensus[cid] = float(np.mean(probs))

    return consensus, group_votes


def _compute_cluster_centers(
    positions: np.ndarray,
    cluster_labels: np.ndarray,
    k: int,
) -> np.ndarray:
    """Compute cluster centers in 2D space.

    Args:
        positions: 2D positions from PCA
        cluster_labels: Cluster assignment for each participant
        k: Number of clusters

    Returns:
        Cluster centers (k, 2)
    """
    centers = np.zeros((k, 2))

    for cluster_id in range(k):
        mask = cluster_labels == cluster_id
        if np.any(mask):
            centers[cluster_id] = positions[mask].mean(axis=0)

    return centers
