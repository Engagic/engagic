"""
Donation API routes for Stripe integration
"""

from fastapi import APIRouter, HTTPException
import stripe

from config import config, get_logger
from server.models.requests import DonateRequest

logger = get_logger(__name__)

router = APIRouter(prefix="/api")


@router.post("/donate/checkout")
async def create_checkout_session(donate_request: DonateRequest):
    """Create a Stripe Checkout session for one-time donations

    Args:
        donate_request: Contains amount in cents

    Returns:
        dict with checkout_url for redirecting user to Stripe Checkout

    Raises:
        HTTPException 500: If Stripe is not configured or session creation fails
        HTTPException 400: If amount validation fails
    """
    if not config.STRIPE_SECRET_KEY:
        logger.error("stripe not configured")
        raise HTTPException(
            status_code=500,
            detail="Payment processing is not configured. Please contact billing@engagic.org"
        )

    try:
        stripe.api_key = config.STRIPE_SECRET_KEY

        amount = donate_request.amount
        logger.info("creating checkout session", amount_cents=amount, amount_dollars=amount/100)

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": "Support Engagic",
                        "description": "One-time donation to support open civic infrastructure",
                    },
                    "unit_amount": amount,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{config.FRONTEND_URL}/about/donate?success=true",
            cancel_url=f"{config.FRONTEND_URL}/about/donate?canceled=true",
        )

        logger.info("checkout session created", session_id=session.id)

        return {
            "checkout_url": session.url,
            "session_id": session.id
        }

    except stripe.StripeError as e:
        logger.error("stripe error", error=str(e), error_type=type(e).__name__)
        raise HTTPException(
            status_code=500,
            detail="Payment processing error. Please try again or contact billing@engagic.org"
        )
    except Exception as e:
        logger.error("unexpected error creating checkout session", error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Unexpected error. Please try again or contact billing@engagic.org"
        )
