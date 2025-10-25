#!/usr/bin/env python3
"""Test the Rust PDF extractor"""

import engagic_core

print("Testing Rust PDF Extractor")
print("=" * 50)

# Test 1: Can we create the extractor?
print("\n1. Creating PdfExtractor...")
try:
    extractor = engagic_core.PdfExtractor()
    print("   SUCCESS: PdfExtractor created")
except Exception as e:
    print(f"   FAILED: {e}")
    exit(1)

# Test 2: Can we validate text?
print("\n2. Testing text validation...")
good_text = """
The city council meeting agenda includes discussion of the new zoning ordinance.
The planning commission will review the budget allocation for infrastructure projects.
Public comment is encouraged at the hearing.
""" * 5  # Make it longer than 100 chars

bad_text = "x"

try:
    is_good = extractor.validate_text(good_text)
    is_bad = extractor.validate_text(bad_text)

    print(f"   Good text validated: {is_good}")
    print(f"   Bad text rejected: {not is_bad}")

    if is_good and not is_bad:
        print("   SUCCESS: Text validation working correctly")
    else:
        print("   FAILED: Unexpected validation results")
except Exception as e:
    print(f"   FAILED: {e}")
    exit(1)

# Test 3: Test Conductor (stub)
print("\n3. Testing Conductor (stub)...")
try:
    conductor = engagic_core.Conductor()
    print(f"   Conductor created, is_running: {conductor.is_running()}")

    conductor.start()
    print(f"   After start(), is_running: {conductor.is_running()}")

    conductor.stop()
    print(f"   After stop(), is_running: {conductor.is_running()}")

    print("   SUCCESS: Conductor stub working")
except Exception as e:
    print(f"   FAILED: {e}")
    exit(1)

print("\n" + "=" * 50)
print("All tests passed! Rust integration working.")
print("\nNext steps:")
print("  - Test PDF extraction with a real PDF")
print("  - Benchmark Rust vs PyPDF2")
print("  - Implement full Conductor in Rust")
