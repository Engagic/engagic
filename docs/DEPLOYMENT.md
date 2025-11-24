# Engagic Deployment Guide

**Last Updated:** 2025-11-01 (Post-Server Refactor)

Operational guide for deploying and managing Engagic on a VPS.

---

## Prerequisites

- VPS with 2GB+ RAM (4GB recommended for stability)
- Ubuntu 22.04+ or Debian 11+
- Python 3.13+
- Root or sudo access

---

## Initial Setup

### 1. Install System Dependencies

```bash
# Update system
apt update && apt upgrade -y

# Install required packages
apt install -y git python3-pip python3-venv curl
```

### 2. Clone Repository

```bash
cd /root
git clone https://github.com/yourusername/engagic.git
cd engagic
```

### 3. Install uv (Python Package Manager)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env
```

### 4. Install Dependencies

```bash
cd /root/engagic
uv sync
```

### 5. Create Data Directory

```bash
mkdir -p /root/engagic/data
```

### 6. Configure Environment Variables

```bash
nano /root/engagic/.env
```

Add the following:

```bash
# Required
GEMINI_API_KEY=your-gemini-api-key-here
ENGAGIC_ADMIN_TOKEN=your-secure-admin-token-here

# Database
ENGAGIC_DB_DIR=/root/engagic/data
ENGAGIC_UNIFIED_DB=/root/engagic/data/engagic.db

# API Server
ENGAGIC_HOST=0.0.0.0
ENGAGIC_PORT=8000
ENGAGIC_DEBUG=false

# Rate Limiting
ENGAGIC_RATE_LIMIT_REQUESTS=30
ENGAGIC_RATE_LIMIT_WINDOW=60

# Background Processing
ENGAGIC_SYNC_INTERVAL_HOURS=72
ENGAGIC_PROCESSING_INTERVAL_HOURS=2

# Logging
ENGAGIC_LOG_LEVEL=INFO
ENGAGIC_LOG_PATH=/root/engagic/engagic.log
```

---

## Systemd Services

### API Server Service

Create `/etc/systemd/system/engagic-api.service`:

```ini
[Unit]
Description=Engagic API Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/engagic
EnvironmentFile=/root/engagic/.env
ExecStart=/root/engagic/.venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Background Daemon Service

Create `/etc/systemd/system/engagic-daemon.service`:

```ini
[Unit]
Description=Engagic Background Daemon
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/engagic
EnvironmentFile=/root/engagic/.env
ExecStart=/root/engagic/.venv/bin/uv run engagic-daemon --daemon
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Enable and Start Services

```bash
# Reload systemd
systemctl daemon-reload

# Enable services (start on boot)
systemctl enable engagic-api engagic-daemon

# Start services
systemctl start engagic-api engagic-daemon

# Check status
systemctl status engagic-api
systemctl status engagic-daemon
```

---

## Nginx Reverse Proxy (Optional)

For SSL/TLS and domain mapping:

```nginx
server {
    listen 80;
    server_name api.engagic.org;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Setup SSL with certbot:

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d api.engagic.org
```

---

## Monitoring

### Health Checks

```bash
# API health
curl http://localhost:8000/api/health

# System metrics
curl http://localhost:8000/api/metrics

# Queue stats
curl http://localhost:8000/api/queue-stats

# Cache stats
curl http://localhost:8000/api/stats
```

### Log Monitoring

```bash
# Follow API logs
journalctl -u engagic-api -f

# Follow daemon logs
journalctl -u engagic-daemon -f

# Last 50 lines of API logs
journalctl -u engagic-api -n 50

# Check log file directly
tail -f /root/engagic/engagic.log
```

### Memory Monitoring

```bash
# Watch memory usage
watch -n 5 'free -m'

# Check process memory
ps aux --sort=-%mem | head -10

# Detailed process view
htop
```

---

## Memory Management

### Expected Usage (2GB RAM VPS)
- Base system: ~200MB
- Uvicorn API: ~100MB
- Daemon (idle): ~200MB
- Daemon (processing): ~400-600MB peak
- **Total stable usage:** 400-600MB

### If Memory Issues Occur

```bash
# Check for OOM kills
dmesg | grep -i "out of memory"

# Check swap usage
free -m

# Restart daemon to clear memory
systemctl restart engagic-daemon

# Monitor memory during processing
watch -n 2 'ps aux | grep python | grep -v grep'
```

### Memory Fixes Applied
- Adapter session cleanup (close HTTP sessions after city sync)
- PDF text cleanup (explicit `del` and `gc.collect()` after processing)
- Forced garbage collection every 10 cities
- BeautifulSoup object cleanup

---

## Updating Code

### Standard Update

```bash
# SSH to VPS
ssh root@your-vps

# Pull latest changes
cd /root/engagic
git pull

# Install new dependencies
uv sync

# Restart services
systemctl restart engagic-api engagic-daemon

# Verify
systemctl status engagic-api
systemctl status engagic-daemon
```

### Database Migrations

If schema changes are required:

```bash
cd /root/engagic
python scripts/migrate_database.py

# Restart services
systemctl restart engagic-api engagic-daemon
```

---

## Backup Strategy

### Automated Daily Backups

```bash
# Create backup directory
mkdir -p /root/engagic/data/backups

# Add to crontab
crontab -e
```

Add these lines:

```cron
# Backup database daily at 3 AM
0 3 * * * cp /root/engagic/data/engagic.db /root/engagic/data/backups/engagic.db.$(date +\%Y\%m\%d)

# Keep only last 7 days
0 4 * * * find /root/engagic/data/backups -name "engagic.db.*" -mtime +7 -delete
```

### Manual Backup

```bash
# Backup database
cp /root/engagic/data/engagic.db /root/engagic/data/engagic.db.backup

# Restore from backup
cp /root/engagic/data/engagic.db.backup /root/engagic/data/engagic.db
systemctl restart engagic-api engagic-daemon
```

---

## Troubleshooting

### API Won't Start

```bash
# Check logs
journalctl -u engagic-api -n 50

# Common issues:
# 1. Missing GEMINI_API_KEY in .env
# 2. Port 8000 already in use (check: lsof -i :8000)
# 3. Database permissions (check: ls -l /root/engagic/data/)
# 4. Missing dependencies (run: uv sync)
```

### Daemon Crashes

```bash
# Check logs
journalctl -u engagic-daemon -n 50

# Common issues:
# 1. Memory exhaustion (check: free -m)
# 2. Database locked (another process accessing?)
# 3. Network issues (check: curl https://google.com)
# 4. Invalid vendor responses
```

### High CPU Usage

```bash
# Check what's consuming CPU
top

# Check queue activity
curl http://localhost:8000/api/queue-stats

# If processing many meetings, high CPU is normal
# Each meeting takes 10-30s of Gemini API time
```

### Database Corruption

```bash
# Check database integrity
sqlite3 /root/engagic/data/engagic.db "PRAGMA integrity_check;"

# If corrupted, restore from backup
systemctl stop engagic-api engagic-daemon
cp /root/engagic/data/backups/engagic.db.YYYYMMDD /root/engagic/data/engagic.db
systemctl start engagic-api engagic-daemon
```

---

## Security Checklist

- [ ] SSL/TLS configured (certbot + nginx)
- [ ] Firewall configured (ufw allow 22,80,443)
- [ ] Strong ENGAGIC_ADMIN_TOKEN set
- [ ] Rate limiting active (30 req/min per IP)
- [ ] SSH key-only authentication
- [ ] Automated backups running
- [ ] Log rotation configured (logrotate)
- [ ] Monitoring/alerting (optional: UptimeRobot)

### Firewall Setup

```bash
# Enable firewall
ufw enable

# Allow SSH, HTTP, HTTPS
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp

# Check status
ufw status
```

---

## Performance Profile

### Expected Performance Metrics

- **API response**: <100ms (cache hit)
- **PDF extraction**: 2-5s per document (PyMuPDF)
- **Item processing**: 10-30s per item (Gemini LLM)
- **Batch processing**: 50% cost savings over individual API calls
- **Background sync**: ~2 hours for 500 cities
- **Memory usage**:
  - API server: ~200MB
  - Background daemon: ~500MB peak
- **Capacity**: 500 cities, ~10K meetings, ~1000 concurrent requests

---

## Performance Tuning

### If API is slow

```bash
# Check cache stats
curl http://localhost:8000/api/stats

# Most queries should be cache hits
# If cache miss rate is high, check daemon sync status
curl http://localhost:8000/api/queue-stats
```

### If Background Sync is slow

```bash
# Check vendor rate limiting in logs
journalctl -u engagic-daemon | grep "Rate limiting"

# Adjust delays in vendors/rate_limiter.py if needed
# Current: 3-5s between vendor requests (respectful)
```

---

## Useful Commands

```bash
# View all engagic processes
ps aux | grep engagic

# Check disk usage
df -h /root/engagic/data

# Database size
ls -lh /root/engagic/data/engagic.db

# Count meetings in database
sqlite3 /root/engagic/data/engagic.db "SELECT COUNT(*) FROM meetings;"

# Count cities
sqlite3 /root/engagic/data/engagic.db "SELECT COUNT(*) FROM cities;"

# Recent logs from both services
journalctl -u engagic-api -u engagic-daemon --since "10 minutes ago"
```

---

## Support

For issues:
1. Check logs: `journalctl -u engagic-api -n 100`
2. Check health: `curl http://localhost:8000/api/health`
3. Check memory: `free -m`
4. Check disk: `df -h`
5. Create GitHub issue with logs and error details
