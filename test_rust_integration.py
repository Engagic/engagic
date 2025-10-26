#!/usr/bin/env python3
"""Test Rust PDF extractor integration with processor

Usage:
    python test_rust_integration.py                    # Run basic integration tests
    python test_rust_integration.py <pdf_url>         # Test full pipeline with real PDF
    python test_rust_integration.py --no-summary <url> # Test extraction only (no LLM)
"""

import os
import sys
import logging
import argparse

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Parse arguments
parser = argparse.ArgumentParser(description='Test Rust PDF extractor integration')
parser.add_argument('pdf_url', nargs='?', help='PDF URL to test with')
parser.add_argument('--no-summary', action='store_true', help='Skip LLM summarization')
parser.add_argument('--banana', default='paloaltoCA', help='City banana for testing (default: paloaltoCA)')
args = parser.parse_args()

print("=" * 70)
print("Testing Rust PDF Extractor Integration")
print("=" * 70)

# Test 1: Import processor with Rust extractor
print("\n1. Testing imports...")
try:
    from backend.core.processor import AgendaProcessor
    print("   SUCCESS: Imported AgendaProcessor")
except Exception as e:
    print(f"   FAILED: {e}")
    sys.exit(1)

# Test 2: Create processor (should initialize Rust extractor)
print("\n2. Creating AgendaProcessor...")
try:
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
print("Basic integration tests passed!")
print("=" * 70)

# Test 5: Full pipeline test with real PDF (if URL provided)
if args.pdf_url:
    print("\n" + "=" * 70)
    print("FULL PIPELINE TEST")
    print("=" * 70)

    pdf_url = args.pdf_url
    print(f"\nPDF URL: {pdf_url}")
    print(f"City: {args.banana}")
    print(f"Skip summary: {args.no_summary}")

    # Test extraction
    print("\n5. Testing PDF extraction...")
    try:
        result = extractor.extract_from_url(pdf_url)

        if result.get('success'):
            text = result.get('text', '')
            print(f"   SUCCESS: Extracted {len(text)} characters")
            print(f"   Method: {result.get('method', 'unknown')}")
            print(f"   Time: {result.get('extraction_time', 0):.2f}s")

            # Show preview
            preview = text[:500].replace('\n', ' ')
            print(f"\n   Preview: {preview}...")

            # Validate
            is_valid = extractor.validate_text(text)
            print(f"   Valid text: {is_valid}")

            if not is_valid:
                print("   WARNING: Extracted text failed validation")
        else:
            print(f"   FAILED: {result.get('error', 'Unknown error')}")
            sys.exit(1)

    except Exception as e:
        print(f"   FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Test full processing with LLM
    if not args.no_summary:
        print("\n6. Testing full processing pipeline (with LLM)...")
        try:
            from backend.core.processor import AgendaProcessor

            # Check if LLM is available
            if not processor.client:
                print("   SKIPPED: No LLM client available (set GEMINI_API_KEY)")
            else:
                meeting_data = {
                    "packet_url": pdf_url,
                    "banana": args.banana,
                    "meeting_name": "Test Meeting",
                    "meeting_date": "2025-10-26",
                    "meeting_id": "test_meeting_001"
                }

                print("   Processing agenda...")
                result = processor.process_agenda_with_cache(meeting_data)

                if result.get('success'):
                    print("   SUCCESS: Generated summary")
                    print(f"   Processing time: {result.get('processing_time', 0):.2f}s")
                    print(f"   Method: {result.get('processing_method', 'unknown')}")

                    summary = result.get('summary', '')
                    if summary:
                        preview = summary[:300].replace('\n', ' ')
                        print(f"\n   Summary preview: {preview}...")

                    # Check cache
                    if result.get('cached'):
                        print("   Result was cached")
                else:
                    print(f"   FAILED: {result.get('error', 'Unknown error')}")

        except Exception as e:
            print(f"   FAILED: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 70)
    print("Full pipeline test complete!")
    print("=" * 70)
else:
    print("\nTo test with a real PDF, run:")
    print(f"  python {sys.argv[0]} <pdf_url>")
    print(f"  python {sys.argv[0]} --no-summary <pdf_url>  # Skip LLM summarization")
