# Engagic Userland - Free Civic Alerts

**One city. 1-3 keywords. Weekly email. Done.**

Free civic alerts with passwordless authentication. Every Sunday at 9am, users get an email with:
1. **Upcoming meetings this week** - All meetings for their city
2. **Your keywords mentioned** - Items mentioning their keywords (optional)

## User Flow

1. Visit city page (`/cities/paloaltoCA`)
2. Click "Get weekly updates" button
3. Enter email + optional 1-3 keywords
4. Verify email via magic link
5. Every Sunday → Receive digest

## Architecture

**Simple UX, Powerful Backend:** Backend supports multi-city, unlimited keywords, daily/weekly frequency. Frontend guides users toward simple single-city, 1-3 keywords, weekly digest.

**Backend (Python/FastAPI):**
- Passwordless auth with magic links (JWT tokens)
- Alert configuration (supports complex use cases)
- Email delivery via Mailgun
- Weekly digest script (keyword matching + upcoming meetings)

**Frontend (SvelteKit):**
- Integrated into main engagic frontend
- "Watch This City" button on city pages
- Dashboard: /dashboard (manage subscription)
- Simple, consumer-friendly UX

## Quick Start

### 1. Setup PostgreSQL Schema

The userland system uses PostgreSQL with a dedicated `userland` schema. First, apply the schema:

```bash
# From project root
python3 -m userland.scripts.setup_db
```

This creates:
- `userland.users` - User accounts
- `userland.alerts` - Alert configurations
- `userland.alert_matches` - Matched meetings/items
- `userland.used_magic_links` - Security table for magic link replay prevention

Safe to run multiple times (uses `IF NOT EXISTS`).

### 2. Environment Variables

```bash
# Generate JWT secret
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'

# Export required variables
export USERLAND_JWT_SECRET="<generated-secret>"
export MAILGUN_API_KEY="<your-key>"
export MAILGUN_DOMAIN="<your-domain>"
export MAILGUN_FROM_EMAIL="digest@yourdomain.com"  # Optional, defaults to alerts@DOMAIN
export FRONTEND_URL="https://engagic.org"          # For magic link emails
export APP_URL="https://engagic.org"               # For weekly digest links
```

Note: Uses main PostgreSQL database with `userland` schema namespace.

### 3. Run Backend

Auth endpoints are integrated into the main FastAPI server (not a separate userland backend):

```bash
# From project root
python server/main.py
# or
uvicorn server.main:app --host 0.0.0.0 --port 8000
```

Backend runs on http://localhost:8000

### 4. Run Frontend

```bash
# From frontend directory
cd frontend
npm install
npm run dev
```

Frontend runs on http://localhost:5173

### 5. Test Flow

**Simple Flow (Recommended):**
1. Visit http://localhost:5173/cities/paloaltoCA (any city)
2. Click "Get weekly updates" button
3. Enter email + name + optional keywords
4. Check email for magic link
5. Click link → Dashboard

**Or signup directly:**
1. Visit http://localhost:5173/signup
2. Sign up with email + name
3. Check email, verify, go to dashboard
4. Add cities/keywords later

### 6. Run Weekly Digest

```bash
# Test weekly digest manually (sends emails to all active users)
sudo systemctl start engagic-digest.service

# Check logs
journalctl -u engagic-digest.service --since "5 minutes ago"
```

**Systemd timer (Sundays at 9am):**
The weekly digest runs automatically via systemd timer:
```bash
# Check timer status
systemctl status engagic-digest.timer

# View next scheduled run
systemctl list-timers | grep engagic
```

## Database Schema

Uses PostgreSQL `userland` namespace. See `database/schema_userland.sql` for full DDL.

### Core Tables

| Table | Purpose |
|-------|---------|
| `userland.users` | User accounts (id, name, email, created_at, last_login) |
| `userland.alerts` | Alert configs (cities JSONB, criteria JSONB, frequency, active) |
| `userland.alert_matches` | Matched meetings/items (match_type, confidence, matched_criteria) |
| `userland.used_magic_links` | Replay attack prevention (token_hash, expires_at) |
| `userland.city_requests` | Coverage expansion tracking (request_count, status) |

### Engagement Tables (Phase 2-3)

| Table | Purpose |
|-------|---------|
| `userland.watches` | User watchlist (matters, meetings, topics, cities, council members) |
| `userland.activity_log` | Activity tracking (views, watches, searches, shares) |
| `userland.trending_matters` | Materialized view, refreshed every 15 min |
| `userland.ratings` | 1-5 star ratings for items/meetings/matters |
| `userland.issues` | User-reported data quality issues |

## API Endpoints

All endpoints prefixed with `/api`.

**Auth** (`/api/auth`):
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/signup` | Create account + send magic link |
| POST | `/login` | Request magic link for existing user |
| GET | `/verify?token=...` | Verify magic link, return tokens |
| POST | `/refresh` | Refresh access token |
| POST | `/logout` | Log out (clear cookies) |
| GET | `/me` | Get current user |
| GET | `/unsubscribe?token=...` | Unsubscribe from digest |
| GET | `/unsubscribe-token` | Get unsubscribe token for current user |

**Dashboard** (`/api/dashboard`):
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/` | Get stats + alerts + recent matches |
| GET | `/stats` | Get subscription stats only |
| GET | `/activity?limit=10` | Get recent activity |
| GET | `/config` | Get user configuration |
| DELETE | `/alert/{id}` | Delete alert |
| PATCH | `/alerts/{id}` | Update alert |
| POST | `/alerts/{id}/keywords` | Add keyword |
| DELETE | `/alerts/{id}/keywords?keyword=...` | Remove keyword |
| POST | `/alerts/{id}/cities` | Add city |
| DELETE | `/alerts/{id}/cities?city=...` | Remove city |

## Admin Utilities

```bash
# Create user manually
python3 -m userland.scripts.create_user \
    --email user@example.com \
    --name "Test User" \
    --cities paloaltoCA \
    --keywords housing zoning

# Send weekly digest manually (sends to all active users)
python3 -m userland.scripts.weekly_digest

# Test all email templates (magic link signup/login + digest with real DB data)
uv run userland/scripts/test_emails.py your@email.com
```

## Weekly Digest Email

**Subject:** This week in [City Name] - X keyword matches

**Content:**
- Section 1: Upcoming meetings (all meetings, next 7 days)
- Section 2: Your keywords mentioned (filtered to keyword matches)

**Frequency:** Sundays at 9am
**No spam:** Only sent if there's content (upcoming meetings or matches)

## Features

- Watch button on city pages - One-click subscription
- Passwordless auth - Magic link login, no passwords
- Simple dashboard - View subscription, recent matches
- Weekly digest - Sunday morning civic updates
- Keyword tracking - 1-3 keywords recommended (unlimited supported)
- Single-city focus - Most users watch one city (multi-city supported)
- One-click unsubscribe - CAN-SPAM compliant, long-lived tokens
- Dual-track matching - String + matter-based (deduplicated legislative items)
- Dark mode emails - Full CSS dark mode support

## Matching Architecture

Dual-track matching for comprehensive coverage:

**String-based** (`match_alert`): Direct keyword search in item summaries. High recall, item-level granularity.

**Matter-based** (`match_matters_for_alert`): Searches deduplicated legislative matters. Same bill in 5 committees = 1 alert (not 5). Includes timeline tracking.

Both run in parallel for every alert via `match_all_alerts_dual_track()`. See `userland/matching/matcher.py`.

## Production Deployment

**Deployed at:** `/opt/engagic` on VPS

**Services:**
- `engagic-api.service` - Main API (includes auth routes)
- `engagic-digest.timer` - Weekly digest (Sundays 9am)

**Environment:** `/opt/engagic/.env`
- `USERLAND_JWT_SECRET` - JWT signing key
- `MAILGUN_API_KEY` - Email delivery
- `MAILGUN_DOMAIN` - Mailgun domain
- `MAILGUN_FROM_EMAIL` - Sender address
- `FRONTEND_URL` - Magic link email URLs
- `APP_URL` - Weekly digest link URLs

---

**Status:** Backend (deployed) | Frontend (deployed) | Weekly Digest (scheduled)
