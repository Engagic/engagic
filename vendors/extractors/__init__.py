"""
Vendors Extractors - Post-processing of adapter data

Extractors take raw vendor data and extract structured information.
Unlike adapters (which fetch data), extractors transform data.

Pattern:
- Adapters: Fetch meetings, items, matters from vendor APIs/HTML
- Extractors: Extract structured entities from adapter output

Current extractors:
- council_member_extractor: Extract sponsor names from matters/items
"""

from vendors.extractors.council_member_extractor import CouncilMemberExtractor

__all__ = ["CouncilMemberExtractor"]
