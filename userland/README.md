# Engagic Userland - Free Civic Alerts

**One city. 1-3 keywords. Weekly email. Done.**

Free civic alerts with passwordless authentication. Every Sunday at 9am, users get an email with:
1. **Upcoming meetings this week** - All meetings for their city
2. **Your keywords mentioned** - Items mentioning their keywords (optional)

## User Flow

1. Visit city page (`/cities/paloaltoCA`)
2. Click "📬 Get weekly updates" button
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
```

Note: `USERLAND_DB` is no longer used - the system now uses the main PostgreSQL database with a `userland` schema.

### 3. Run Backend

```bash
# From project root
python3 -m userland.server.main
```

Backend runs on http://localhost:8001

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
2. Click "📬 Get weekly updates" button
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
# Test weekly digest (sends emails to all active users)
python3 -m userland.scripts.weekly_digest
```

**Cron setup (Sundays at 9am):**
```bash
0 9 * * 0 cd /root/engagic && .venv/bin/python -m userland.scripts.weekly_digest >> /var/log/userland_digest.log 2>&1
```

## Database Schema

### users
- `id`, `name`, `email`, `created_at`, `last_login`

### alerts
- `id`, `user_id`, `name`, `cities` (JSON), `criteria` (JSON), `frequency`, `active`, `created_at`

### alert_matches
- `id`, `alert_id`, `meeting_id`, `item_id`, `match_type`, `confidence`, `matched_criteria`, `notified`, `created_at`

## API Endpoints

**Auth:**
- `POST /auth/signup` - Create account
- `POST /auth/login` - Request magic link
- `GET /auth/verify?token=...` - Verify magic link
- `POST /auth/refresh` - Refresh access token
- `POST /auth/logout` - Log out

**Dashboard:**
- `GET /dashboard` - Get stats, alerts, and recent matches
- `PATCH /dashboard/alerts/{id}` - Update alert
- `POST /dashboard/alerts/{id}/keywords` - Add keyword
- `DELETE /dashboard/alerts/{id}/keywords` - Remove keyword
- `POST /dashboard/alerts/{id}/cities` - Add city
- `DELETE /dashboard/alerts/{id}/cities` - Remove city

## Admin Utilities

```bash
# Create user manually
python3 -m userland.scripts.create_user \
    --email user@example.com \
    --name "Test User"

# Send weekly digest manually (test)
python3 -m userland.scripts.weekly_digest
```

## Weekly Digest Email

**Subject:** This week in [City Name] - X keyword matches

**Content:**
- Section 1: Upcoming meetings (all meetings, next 7 days)
- Section 2: Your keywords mentioned (filtered to keyword matches)

**Frequency:** Sundays at 9am
**No spam:** Only sent if there's content (upcoming meetings or matches)

## Features

✅ **Watch button on city pages** - One-click subscription
✅ **Passwordless auth** - Magic link login, no passwords
✅ **Simple dashboard** - View subscription, recent matches
✅ **Weekly digest** - Sunday morning civic updates
✅ **Keyword tracking** - 1-3 keywords recommended (unlimited supported)
✅ **Single-city focus** - Most users watch one city (multi-city supported for power users)

## Next Steps

- [ ] Deploy to production VPS
- [ ] Set up Mailgun for production emails
- [ ] Monitor email deliverability and open rates
- [ ] Add unsubscribe flow

---

**Status:** Backend ✅ | Frontend ✅ | Integration ✅

**Ready to deploy!** Simple Sunday digest for civic engagement.
