#!/usr/bin/env python3
"""
Test script for Gemini processor
Usage: python test_gemini.py [pdf_url]
"""

import sys
import os
import logging

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.core.gemini_processor import GeminiProcessor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("engagic")


def test_basic_connection():
    """Test basic Gemini API connection"""
    print("\n=== Testing Gemini API Connection ===")
    try:
        processor = GeminiProcessor()
        print("✓ Successfully initialized Gemini processor")
        print(f"✓ Using models: {processor.flash_model_name} and {processor.flash_lite_model_name}")
        return True
    except Exception as e:
        print(f"✗ Failed to initialize: {e}")
        return False


def test_pdf_processing(url):
    """Test PDF processing with a real URL"""
    print(f"\n=== Testing PDF Processing ===")
    print(f"URL: {url}")
    
    try:
        processor = GeminiProcessor()
        
        # Test the processing
        summary, method = processor.process_agenda_optimal(url)
        
        print(f"\n✓ Successfully processed PDF")
        print(f"✓ Method used: {method}")
        print(f"✓ Summary length: {len(summary)} characters")
        print("\n=== Summary Preview (first 500 chars) ===")
        print(summary[:500])
        print("...")
        
        return True
        
    except Exception as e:
        print(f"✗ Failed to process PDF: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("Gemini Processor Test Suite")
    print("=" * 50)
    
    # Check for API key
    if not os.getenv("GEMINI_API_KEY") and not os.getenv("LLM_API_KEY"):
        print("\n⚠️  Warning: No GEMINI_API_KEY or LLM_API_KEY environment variable found")
        print("Set one of these before running tests:")
        print("  export GEMINI_API_KEY='your-api-key'")
        return
    
    # Test basic connection
    if not test_basic_connection():
        print("\nBasic connection test failed. Please check your API key.")
        return
    
    # Test PDF processing if URL provided
    if len(sys.argv) > 1:
        pdf_url = sys.argv[1]
        test_pdf_processing(pdf_url)
    else:
        print("\n💡 Tip: Provide a PDF URL to test full processing:")
        print("   python test_gemini.py https://example.com/agenda.pdf")
    
    print("\n" + "=" * 50)
    print("Test complete!")


if __name__ == "__main__":
    main()