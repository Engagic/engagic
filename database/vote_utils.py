"""Shared vote tally and outcome computation logic."""

from typing import Dict, List

# Canonical vote value mappings
VOTE_MAP = {
    "yes": "yes",
    "aye": "yes",
    "yea": "yes",
    "no": "no",
    "nay": "no",
    "abstain": "abstain",
    "abstained": "abstain",
    "absent": "absent",
    "excused": "absent",
    "not present": "absent",
    "present": "present",
    "recused": "abstain",
    "not_voting": "present",
}


def compute_vote_tally(votes: List[Dict]) -> Dict[str, int]:
    """Compute vote tally from raw vote data."""
    tally = {"yes": 0, "no": 0, "abstain": 0, "absent": 0, "present": 0}

    for vote in votes:
        vote_value = vote.get("vote", "").lower().strip()
        normalized = VOTE_MAP.get(vote_value, "present")
        tally[normalized] += 1

    return tally


def determine_vote_outcome(tally: Dict[str, int]) -> str:
    """Determine vote outcome from tally. Returns passed, failed, tabled, or no_vote."""
    yes_count = tally.get("yes", 0)
    no_count = tally.get("no", 0)

    if yes_count == 0 and no_count == 0:
        return "no_vote"
    if yes_count > no_count:
        return "passed"
    if no_count > yes_count:
        return "failed"
    return "tabled"  # Tie
