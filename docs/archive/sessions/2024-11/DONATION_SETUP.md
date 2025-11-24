# Donation System Setup Guide

## Overview

Your donation page now supports:
- **One-time donations** via Stripe Checkout (preset amounts: $5, $15, $30, $50, $100 + custom)
- **Recurring donations** via Liberapay widget

## What Was Implemented

### Backend Changes
1. **Config (`config.py`)**
   - Added `STRIPE_SECRET_KEY` environment variable
   - Added `STRIPE_PUBLISHABLE_KEY` environment variable (for future use)
   - Added `FRONTEND_URL` environment variable (defaults to https://engagic.org)

2. **Dependencies (`pyproject.toml`)**
   - Added `stripe>=11.3.0` package

3. **API Route (`server/routes/donate.py`)**
   - New endpoint: `POST /api/donate/checkout`
   - Creates Stripe Checkout Session
   - Returns checkout URL for redirect
   - Handles errors gracefully

4. **Request Model (`server/models/requests.py`)**
   - New `DonateRequest` model
   - Validates amount (min $1.00, max $10,000.00)

### Frontend Changes
1. **Donate Page (`frontend/src/routes/about/donate/+page.svelte`)**
   - Replaced GitHub Sponsors and Ko-fi buttons
   - Added preset amount buttons ($5, $15, $30, $50, $100)
   - Added custom amount input field
   - Integrated Stripe Checkout flow
   - Added Liberapay widget for recurring donations
   - Success/cancel message handling
   - Loading states and error messages

## Setup Instructions

### 1. Install Dependencies

On your **VPS**, run:

```bash
cd /root/engagic
uv pip install stripe
# Or if using regular pip:
# pip install stripe
```

### 2. Set Environment Variables

On your **VPS**, add these to your environment (e.g., in `~/.bashrc` or systemd service file):

```bash
# Stripe Configuration
export STRIPE_SECRET_KEY="sk_test_..."  # Replace with your actual key
export STRIPE_PUBLISHABLE_KEY="pk_test_..."  # Optional, for future use

# Frontend URL (for redirects after payment)
export ENGAGIC_FRONTEND_URL="https://engagic.org"  # Or your actual frontend URL
```

**Where to get these:**
- Stripe Secret Key: https://dashboard.stripe.com/test/apikeys
- For production, use live mode keys (starts with `sk_live_`)

### 3. Test the Backend

Start your API server and test the donate endpoint:

```bash
# Start the server
cd /root/engagic
python server/main.py

# In another terminal, test the endpoint
curl -X POST http://localhost:8000/api/donate/checkout \
  -H "Content-Type: application/json" \
  -d '{"amount": 1000}'

# Should return something like:
# {"checkout_url": "https://checkout.stripe.com/c/pay/cs_test_...", "session_id": "cs_test_..."}
```

### 4. Deploy Frontend

On your **local machine**, build and deploy the frontend:

```bash
cd frontend
npm run build
# Deploy to Cloudflare Pages (or your hosting platform)
```

### 5. Test the Full Flow

1. Visit: https://engagic.org/about/donate
2. Click a preset amount or enter a custom amount
3. Click "Donate via Stripe"
4. Should redirect to Stripe Checkout
5. Use test card: `4242 4242 4242 4242`, any future expiry, any CVC
6. Complete payment
7. Should redirect back to: https://engagic.org/about/donate?success=true
8. See success message

### 6. Test Liberapay

1. On the donate page, click the Liberapay button in the "Monthly Support" card
2. Should open Liberapay's donation page for your account

## Production Checklist

- [ ] Set `STRIPE_SECRET_KEY` with **live mode** key (starts with `sk_live_`)
- [ ] Set `STRIPE_PUBLISHABLE_KEY` with live mode key (starts with `pk_live_`)
- [ ] Set `ENGAGIC_FRONTEND_URL` to your production frontend URL
- [ ] Restart API server after setting environment variables
- [ ] Test donation flow end-to-end with real card
- [ ] Verify Liberapay button works
- [ ] Check that success/cancel redirects work correctly
- [ ] Monitor Stripe Dashboard for incoming payments

## Stripe Test Cards

**Success:**
- `4242 4242 4242 4242` - Successful payment
- Any future expiry date
- Any 3-digit CVC
- Any ZIP code

**Decline:**
- `4000 0000 0000 0002` - Card declined
- `4000 0000 0000 9995` - Insufficient funds

Full list: https://stripe.com/docs/testing

## Troubleshooting

### "Payment processing is not configured" error
- Ensure `STRIPE_SECRET_KEY` environment variable is set
- Restart API server after setting environment variables

### Checkout session creation fails
- Check API server logs for Stripe errors
- Verify Stripe key is correct (test vs live mode)
- Ensure amount is between $1.00 and $10,000.00

### Redirect doesn't work after payment
- Verify `ENGAGIC_FRONTEND_URL` is set correctly
- Check CORS settings allow your frontend domain

### Liberapay button doesn't appear
- Check browser console for JavaScript errors
- Verify Liberapay account name is "engagic"
- Ensure script tag loads: `https://liberapay.com/engagic/widgets/button.js`

## Architecture Notes

### Flow
1. User selects amount on frontend
2. Frontend calls `POST /api/donate/checkout` with amount in cents
3. Backend creates Stripe Checkout Session
4. Backend returns checkout URL
5. Frontend redirects to Stripe hosted checkout page
6. User completes payment on Stripe
7. Stripe redirects back to frontend with success/cancel parameter
8. Frontend shows success/cancel message

### Security
- Secret key never exposed to frontend
- Backend validates all amounts (min/max limits)
- Stripe handles all payment processing
- PCI compliance handled by Stripe

### Cost
- Stripe fee: 2.9% + $0.30 per transaction
- No monthly fees
- Liberapay: voluntary fees (0-10% chosen by user)

## Future Enhancements

Possible additions:
- Stripe webhook to record donations in database
- Email receipts (Stripe sends these automatically)
- Donation history for users
- Donor recognition page
- Preset recurring amounts via Stripe Billing
- Apple Pay / Google Pay support (Stripe Checkout supports these automatically)

## Support

Questions? Contact:
- Stripe Support: https://support.stripe.com
- Liberapay Support: https://liberapay.com/about/contact
- Engagic: billing@engagic.org
