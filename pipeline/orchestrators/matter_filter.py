"""Matter Filter - Decides which matter types to track"""

from pipeline.filters import should_skip_matter


class MatterFilter:
    """Filters out administrative/procedural matter types"""

    def should_skip(self, matter_type: str | None) -> bool:
        """Check if matter should be skipped based on its type"""
        return should_skip_matter(matter_type) if matter_type else False
