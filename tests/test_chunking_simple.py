import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

#!/usr/bin/env python3
"""Simple test for PDF chunking"""

import os
os.environ['LLM_API_KEY'] = os.environ.get('LLM_API_KEY', '')

from backend.core.processor import AgendaProcessor

# Test URL - this is a large PDF that should trigger chunking
test_url = "https://d3n9y02raazwpg.cloudfront.net/astoria/aeddbc3d-be45-11ef-ab4b-005056a89546-6b919134-5222-4f0e-b597-94c89be5e07d-1752086857.pdf"

print("Testing chunking with large PDF...")
print(f"URL: {test_url[:80]}...")

try:
    processor = AgendaProcessor()
    
    # Force chunked method
    print("\nTesting direct chunked method...")
    summary = processor.process_agenda(test_url, pdf_method="chunked", save_raw=False)
    print(f"✓ Success! Summary length: {len(summary)} chars")
    print(f"\nFirst 300 chars:\n{summary[:300]}...")
    
except Exception as e:
    print(f"✗ Failed: {e}")
    import traceback
    traceback.print_exc()