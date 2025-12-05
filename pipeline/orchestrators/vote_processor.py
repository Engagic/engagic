"""Vote Processor - Computes tallies and outcomes"""

from typing import List, Dict, Any

from database.vote_utils import compute_vote_tally, determine_vote_outcome


class VoteProcessor:
    """Processes votes and determines outcomes"""

    def process_votes(self, votes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process votes and return tally + outcome"""
        tally = compute_vote_tally(votes)
        return {"tally": tally, "outcome": determine_vote_outcome(tally)}

    def compute_tally(self, votes: List[Dict[str, Any]]) -> Dict[str, int]:
        """Compute vote tally without determining outcome"""
        return compute_vote_tally(votes)

    def determine_outcome(self, tally: Dict[str, int]) -> str:
        """Determine outcome from vote tally"""
        return determine_vote_outcome(tally)
