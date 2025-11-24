# Userland Deployment Guide

## VPS Setup (One-time)

### 1. Apply Database Schema

SSH to VPS and run the schema setup:

```bash
ssh root@engagic
cd /root/engagic

# Apply userland schema to PostgreSQL
python3 -m userland.scripts.setup_db
```

Expected output:
```
Connecting to PostgreSQL database...
Database: localhost:5432/engagic

Applying userland schema from /root/engagic/database/schema_userland.sql...

Schema applied successfully!

Verifying tables...

Userland tables created:
  - userland.alert_matches
  - userland.alerts
  - userland.used_magic_links
  - userland.users

Current data:
  - Users: 0
  - Alerts: 0

Database connection closed.
```

Safe to run multiple times (uses `IF NOT EXISTS`).

### 2. Verify Environment Variables

Ensure these variables are set in `/root/.bashrc` or systemd service file:

```bash
# Required
export USERLAND_JWT_SECRET="<your-secret-key>"
export MAILGUN_API_KEY="<your-mailgun-key>"
export MAILGUN_DOMAIN="<your-domain>"

# PostgreSQL (should already be set for main engagic)
export ENGAGIC_USE_POSTGRES="true"
export ENGAGIC_POSTGRES_HOST="localhost"
export ENGAGIC_POSTGRES_PORT="5432"
export ENGAGIC_POSTGRES_DB="engagic"
export ENGAGIC_POSTGRES_USER="engagic"
export ENGAGIC_POSTGRES_PASSWORD="<your-password>"
```

### 3. Test Signup Flow

Restart the API service and test:

```bash
sudo systemctl restart engagic-api

# Test signup endpoint
curl -X POST https://api.engagic.org/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","name":"Test User"}'
```

Should return 200 with user creation success (or 400 if email exists).

### 4. Setup Weekly Digest Cron

Add to crontab for weekly civic alerts:

```bash
crontab -e

# Add this line (Sundays at 9am)
0 9 * * 0 cd /root/engagic && .venv/bin/python -m userland.scripts.weekly_digest >> /var/log/userland_digest.log 2>&1
```

## Troubleshooting

### Schema Already Exists
Safe to ignore - script uses `IF NOT EXISTS`.

### Connection Errors
- Check PostgreSQL is running: `sudo systemctl status postgresql`
- Verify credentials in environment variables
- Test connection: `psql -U engagic -d engagic -c "SELECT 1"`

### Missing Environment Variables
- Check: `echo $USERLAND_JWT_SECRET`
- Reload: `source /root/.bashrc` or restart service

### Table Access Errors
- Check schema exists: `psql -U engagic -d engagic -c "\dn"`
- Check tables: `psql -U engagic -d engagic -c "\dt userland.*"`

## Rollback (Emergency)

If needed, drop the userland schema:

```sql
-- WARNING: Destroys all user data
DROP SCHEMA userland CASCADE;
```

Then re-run setup script to recreate.
