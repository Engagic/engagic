"""
Topic Normalization for Engagic

Maps AI-extracted topics to canonical taxonomy for consistency.
Handles variations like "affordable housing" -> "housing", "rezoning" -> "zoning"
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger("engagic")


class TopicNormalizer:
    """Normalizes extracted topics to canonical taxonomy"""

    def __init__(self, taxonomy_path: Optional[str] = None):
        """
        Initialize normalizer with taxonomy

        Args:
            taxonomy_path: Path to topic_taxonomy.json (defaults to same directory)
        """
        if taxonomy_path is None:
            taxonomy_path = Path(__file__).parent / "topic_taxonomy.json"

        with open(taxonomy_path, "r") as f:
            data = json.load(f)

        self.taxonomy = data["taxonomy"]
        self.prompt_examples = data["prompt_examples"]

        # Build reverse lookup: synonym -> canonical
        self._synonym_map = {}
        for canonical_key, topic_data in self.taxonomy.items():
            canonical = topic_data["canonical"]

            # Map canonical to itself
            self._synonym_map[canonical.lower()] = canonical

            # Map all synonyms to canonical
            for synonym in topic_data.get("synonyms", []):
                self._synonym_map[synonym.lower()] = canonical

        logger.info(
            f"Loaded topic taxonomy: {len(self.taxonomy)} categories, "
            f"{len(self._synonym_map)} total mappings"
        )

    def normalize(self, topics: List[str]) -> List[str]:
        """
        Normalize a list of topics to canonical forms

        Args:
            topics: Raw topics from AI extraction

        Returns:
            List of canonical topics (deduplicated)

        Examples:
            >>> normalizer.normalize(["affordable housing", "zoning changes", "parks"])
            ["housing", "zoning", "parks"]
        """
        if not topics:
            return []

        canonical_topics = set()

        for topic in topics:
            if not topic:
                continue

            topic_lower = topic.strip().lower()

            # Direct match
            if topic_lower in self._synonym_map:
                canonical_topics.add(self._synonym_map[topic_lower])
            else:
                # Partial match (e.g., "affordable housing plan" -> "housing")
                matched = False
                for synonym, canonical in self._synonym_map.items():
                    if synonym in topic_lower or topic_lower in synonym:
                        canonical_topics.add(canonical)
                        matched = True
                        break

                if not matched:
                    # No match - log for future taxonomy expansion
                    logger.debug(
                        f"[TopicNormalizer] Unknown topic: '{topic}' - consider adding to taxonomy"
                    )
                    # Keep original but normalized
                    canonical_topics.add(topic_lower)

        result = sorted(list(canonical_topics))
        logger.debug(f"[TopicNormalizer] {topics} -> {result}")
        return result

    def normalize_single(self, topic: str) -> str:
        """
        Normalize a single topic

        Args:
            topic: Raw topic string

        Returns:
            Canonical topic or original if no match
        """
        if not topic:
            return ""

        topic_lower = topic.strip().lower()

        # Direct match
        if topic_lower in self._synonym_map:
            return self._synonym_map[topic_lower]

        # Partial match
        for synonym, canonical in self._synonym_map.items():
            if synonym in topic_lower or topic_lower in synonym:
                return canonical

        # No match - return normalized original
        return topic_lower

    def get_display_name(self, canonical_topic: str) -> str:
        """
        Get human-friendly display name for a canonical topic

        Args:
            canonical_topic: Canonical form (e.g., "public_safety")

        Returns:
            Display name (e.g., "Public Safety")
        """
        for topic_data in self.taxonomy.values():
            if topic_data["canonical"] == canonical_topic:
                return topic_data["display_name"]

        # Fallback: title case the canonical
        return canonical_topic.replace("_", " ").title()

    def get_all_canonical_topics(self) -> List[str]:
        """Get list of all canonical topics for frontend/API"""
        return [data["canonical"] for data in self.taxonomy.values()]

    def get_prompt_examples(self) -> str:
        """Get topic examples for LLM prompt"""
        return ", ".join(self.prompt_examples)


# Global instance
_normalizer = None


def get_normalizer() -> TopicNormalizer:
    """Get global normalizer instance"""
    global _normalizer
    if _normalizer is None:
        _normalizer = TopicNormalizer()
    return _normalizer
