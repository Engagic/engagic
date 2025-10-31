#!/usr/bin/env python3
"""Test Rust PDF extractor integration with processor"""

import sys
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

print("=" * 70)
print("Testing Rust PDF Extractor Integration")
print("=" * 70)

# Test 1: Import processor with Rust extractor
print("\n1. Testing imports...")
try:
    print(sys.path)
    from backend i
    print("   SUCCESS: Imported AgendaProcessor")
except Exception as e:
    print(f"   FAILED: {e}")
    sys.exit(1)

# Test 2: Create processor (should initialize Rust extractor)
print("\n2. Creating AgendaProcessor...")
try:
    import os
    os.environ['GEMINI_API_KEY'] = os.getenv('GEMINI_API_KEY') or 'test-key'
    processor = AgendaProcessor()
    print("   SUCCESS: Processor created")
    print(f"   - Has pdf_extractor: {hasattr(processor, 'pdf_extractor')}")
    print(f"   - Extractor type: {type(processor.pdf_extractor).__name__}")
except Exception as e:
    print(f"   FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Check Rust extractor methods
print("\n3. Checking Rust extractor methods...")
try:
    extractor = processor.pdf_extractor
    has_extract_url = hasattr(extractor, 'extract_from_url')
    has_extract_bytes = hasattr(extractor, 'extract_from_bytes')
    has_validate = hasattr(extractor, 'validate_text')

    print(f"   - extract_from_url: {has_extract_url}")
    print(f"   - extract_from_bytes: {has_extract_bytes}")
    print(f"   - validate_text: {has_validate}")

    if all([has_extract_url, has_extract_bytes, has_validate]):
        print("   SUCCESS: All methods present")
    else:
        print("   FAILED: Missing methods")
        sys.exit(1)
except Exception as e:
    print(f"   FAILED: {e}")
    sys.exit(1)

# Test 4: Test validation (lightweight test)
print("\n4. Testing text validation...")
try:
    good_text = "The city council meeting agenda includes public comment. " * 10
    bad_text = "x"

    is_good = extractor.validate_text(good_text)
    is_bad = extractor.validate_text(bad_text)

    print(f"   - Good text validated: {is_good}")
    print(f"   - Bad text rejected: {not is_bad}")

    if is_good and not is_bad:
        print("   SUCCESS: Validation working correctly")
    else:
        print("   FAILED: Unexpected validation results")
        sys.exit(1)
except Exception as e:
    print(f"   FAILED: {e}")
    sys.exit(1)

print("\n" + "=" * 70)
print("All integration tests passed!")
print("=" * 70)
print("\nNext: Test with a real meeting PDF")
print("Example: python test_with_real_pdf.py <pdf_url>")
