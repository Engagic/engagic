"""
Premium Processing Tiers - ARCHIVED (Phase 3 - 2025-01-23)

This code is archived but preserved for future re-enablement when paid customers exist.

CONTEXT:
- Tier 1 (PyPDF2 + Gemini): 60% success rate, fast, cheap - ACTIVE for free tier
- Tier 2 (Mistral OCR + Gemini): 15% additional success, slow, expensive - ARCHIVED
- Tier 3 (Gemini PDF API): 95% success, very slow, very expensive - ARCHIVED

WHY ARCHIVED:
- No paid customers yet
- Free tier should fail fast (don't waste time on fallbacks)
- Tier 2/3 add complexity for marginal value without revenue
- Cost per document too high without paying customers

HOW TO RE-ENABLE:
1. Add feature flag to config.py: ENABLE_PREMIUM_TIERS = True
2. Copy tier 2/3 methods back to AgendaProcessor in processor.py
3. Update process_agenda_optimal() to check feature flag
4. Add tier selection based on user subscription level
5. Re-add mistralai to dependencies in pyproject.toml

EXPECTED USE CASE:
- Paid tier customers who need higher success rates
- Government clients who need 95%+ coverage
- Enterprise customers processing difficult scanned documents
"""

import os
import logging
import tempfile
import base64
from typing import Optional

logger = logging.getLogger("engagic")


def tier2_mistral_ocr(self, url: str) -> Optional[str]:
    """
    Tier 2: Use Mistral OCR API for text extraction

    SUCCESS RATE: +15% over Tier 1 (75% total)
    COST: ~$0.02 per document
    SPEED: ~15-20 seconds

    WHEN TO USE:
    - Paid tier customers
    - Scanned PDFs where Tier 1 failed
    - Documents with complex layouts

    Args:
        self: AgendaProcessor instance (must have self.mistral_client)
        url: PDF URL to process

    Returns:
        Extracted text or None
    """
    if not self.mistral_client:
        return None

    try:
        # Download PDF first
        pdf_content = self._download_pdf(url)
        if not pdf_content:
            return None

        # Convert to base64 for Mistral API
        pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')

        # Call Mistral OCR API
        response = self.mistral_client.chat.complete(
            model="mistral-ocr-latest",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract all text from this PDF document. Preserve the structure and formatting."},
                    {"type": "pdf", "pdf": pdf_base64}
                ]
            }]
        )

        text = response.choices[0].message.content
        logger.info(f"Mistral OCR extracted {len(text)} characters")

        return self._normalize_text(text) if text else None

    except Exception as e:
        logger.error(f"Mistral OCR failed: {e}")
        return None


def tier3_gemini_pdf_api(self, url: str) -> Optional[str]:
    """
    Tier 3: Use Gemini's native PDF processing

    SUCCESS RATE: 95%+ (highest quality)
    COST: ~$0.03-0.05 per document
    SPEED: ~20-30 seconds

    WHEN TO USE:
    - Premium tier customers
    - When Tier 1 and Tier 2 both failed
    - Critical documents requiring highest accuracy
    - Scanned documents with poor quality

    Args:
        self: AgendaProcessor instance
        url: PDF URL to process

    Returns:
        Summary text or None
    """
    try:
        # Download PDF
        pdf_content = self._download_pdf(url)
        if not pdf_content:
            return None

        # Upload PDF to Gemini
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
            tmp_file.write(pdf_content)
            tmp_path = tmp_file.name

        try:
            # Upload file to Gemini
            uploaded_file = self.client.files.upload(file=tmp_path)
            logger.info(f"Uploaded PDF to Gemini: {uploaded_file.name}")

            # Determine which model to use based on PDF size
            pdf_size = len(pdf_content)
            if pdf_size < 5 * 1024 * 1024:  # Under 5MB - use Flash-Lite
                model_name = self.flash_lite_model_name
                model_display = "flash-lite"
            else:
                model_name = self.flash_model_name
                model_display = "flash"

            # Generate summary directly from PDF
            from google.genai import types
            prompt = self._get_comprehensive_prompt()

            # PDF API: Use moderate thinking since we're asking for complex analysis
            config = types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=8192,
                thinking_config=types.ThinkingConfig(thinking_budget=4096)  # Moderate thinking for analysis
            )

            response = self.client.models.generate_content(
                model=model_name,
                contents=[uploaded_file, prompt],
                config=config
            )

            logger.info(f"Gemini PDF API ({model_display}) generated summary")
            return response.text

        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    except Exception as e:
        logger.error(f"Gemini PDF API failed: {e}")
        return None


# INTEGRATION EXAMPLE:
# How to integrate these tiers back into processor.py when you have paid customers

INTEGRATION_EXAMPLE = """
# In processor.py, update process_agenda_optimal():

def process_agenda_optimal(self, url: Union[str, List[str]], tier_level: str = "free") -> tuple[str, str]:
    '''
    Process agenda using appropriate tier based on subscription level

    Args:
        url: PDF URL to process
        tier_level: "free", "paid", or "premium"
    '''
    # Tier 1: Always try fast extraction first
    logger.info(f"Attempting Tier 1: PyPDF2 text extraction + Gemini for {url}...")
    try:
        text = self._tier1_extract_text(url)
        if text and self._is_good_text_quality(text):
            summary = self._summarize_with_gemini(text)
            logger.info("Tier 1 successful - PyPDF2 + Gemini")
            return summary, "tier1_pypdf2_gemini"
    except Exception as e:
        logger.warning(f"Tier 1 failed: {type(e).__name__}: {str(e)}")

    # Free tier: fail fast, no fallback
    if tier_level == "free":
        logger.info("Free tier - no fallback available")
        raise ProcessingError("Document requires paid tier for processing")

    # Tier 2: Mistral OCR (paid tier only)
    if tier_level in ["paid", "premium"] and self.mistral_client:
        logger.info(f"Attempting Tier 2: Mistral OCR + Gemini for {url}...")
        try:
            text = tier2_mistral_ocr(self, url)
            if text and self._is_good_text_quality(text):
                summary = self._summarize_with_gemini(text)
                logger.info("Tier 2 successful - Mistral OCR + Gemini")
                return summary, "tier2_mistral_gemini"
        except Exception as e:
            logger.warning(f"Tier 2 failed: {type(e).__name__}: {str(e)}")

    # Tier 3: Gemini PDF API (premium tier only)
    if tier_level == "premium":
        logger.info(f"Attempting Tier 3: Direct Gemini PDF API for {url}...")
        try:
            summary = tier3_gemini_pdf_api(self, url)
            if summary:
                logger.info("Tier 3 successful - Gemini PDF API")
                return summary, "tier3_gemini_pdf_api"
        except Exception as e:
            logger.error(f"Tier 3 failed: {type(e).__name__}: {str(e)}")

    # All available tiers failed
    raise ProcessingError(f"All available tiers failed for tier_level={tier_level}")
"""

# PRICING SUGGESTION:
PRICING_TIERS = """
Free Tier:
- Tier 1 only (PyPDF2 + Gemini)
- 60% success rate
- Fail fast if document can't be processed
- Good for well-formatted digital PDFs
- Cost: ~$0.001 per document

Paid Tier ($20/month):
- Tier 1 + Tier 2 (Mistral OCR)
- 75% success rate
- Better for scanned documents
- Cost: ~$0.01-0.02 per document

Premium Tier ($100/month):
- Tier 1 + Tier 2 + Tier 3 (Gemini PDF)
- 95%+ success rate
- Best for difficult documents
- Cost: ~$0.03-0.05 per document
"""
