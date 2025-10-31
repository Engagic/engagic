# VPS Migration Checklist (Post-Reorganization)

**Date:** 2025-10-30

This checklist covers deploying the reorganized codebase to your VPS.

---

## Pre-Migration Checklist

On your **local machine** (before pushing):

- [x] All imports updated (no `infocore.*` or `jobs.*`)
- [x] Old directories deleted (`infocore/`, `jobs/`, `infra/`)
- [x] Documentation updated (CLAUDE.md, README.md, DEPLOYMENT.md)
- [x] New structure verified (vendors/, parsing/, analysis/, pipeline/, database/, server/)
- [ ] Git commit all changes
- [ ] Git push to GitHub

---

## VPS Migration Steps

SSH to your VPS: `ssh root@engagic`

### 1. Backup Current Database ✅

```bash
# Create backup
cp /root/engagic/data/engagic.db /root/engagic/data/engagic.db.pre-reorganization-backup

# Verify backup
ls -lh /root/engagic/data/engagic.db*
```

### 2. Stop Running Services ✅

```bash
# Stop both services
systemctl stop engagic-api
systemctl stop engagic-daemon

# Verify stopped
systemctl status engagic-api
systemctl status engagic-daemon
```

### 3. Pull New Code ✅

```bash
cd /root/engagic

# Pull changes
git pull

# Verify new structure
ls -la | grep -E "vendors|parsing|analysis|pipeline|database|server"

# Old directories should be gone
ls -la | grep -E "infocore|jobs|infra"  # Should return nothing
```

### 4. Update systemd Service Files ✅

**Edit API service:**
```bash
nano /etc/systemd/system/engagic-api.service
```

Change:
```ini
# OLD
ExecStart=/root/engagic/.venv/bin/uvicorn infocore.api.main:app --host 0.0.0.0 --port 8000

# NEW
ExecStart=/root/engagic/.venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000
```

**Edit Daemon service:**
```bash
nano /etc/systemd/system/engagic-daemon.service
```

Change:
```ini
# OLD
ExecStart=/root/engagic/.venv/bin/python -m infra.daemon
# OR
ExecStart=/root/engagic/.venv/bin/python -m jobs.conductor

# NEW
ExecStart=/root/engagic/.venv/bin/python -m pipeline.conductor
```

**Reload systemd:**
```bash
systemctl daemon-reload
```

### 5. Install Dependencies (if needed) ✅

```bash
cd /root/engagic

# Update dependencies
uv sync

# Verify installation
ls -la .venv/bin/python
```

### 6. Test Import Chain ✅

Quick test to verify imports work:

```bash
cd /root/engagic

# Test imports
python3 -c "from database.db import UnifiedDatabase; print('✅ database.db')"
python3 -c "from vendors.factory import get_adapter; print('✅ vendors.factory')"
python3 -c "from parsing.pdf import PdfExtractor; print('✅ parsing.pdf')"
python3 -c "from analysis.llm.summarizer import GeminiSummarizer; print('✅ analysis.llm.summarizer')"
python3 -c "from pipeline.processor import AgendaProcessor; print('✅ pipeline.processor')"
python3 -c "from server.main import app; print('✅ server.main')"

# If all print ✅, imports are good!
```

### 7. Start Services ✅

```bash
# Start services
systemctl start engagic-api
systemctl start engagic-daemon

# Check status (should be active/running)
systemctl status engagic-api
systemctl status engagic-daemon
```

### 8. Monitor Startup Logs ✅

**In separate terminals/tmux panes:**

```bash
# Terminal 1: Watch API logs
journalctl -u engagic-api -f

# Terminal 2: Watch daemon logs
journalctl -u engagic-daemon -f
```

**Look for:**
- ✅ No import errors
- ✅ Database connection successful
- ✅ API server started on port 8000
- ✅ Daemon sync cycle started

**Red flags:**
- ❌ `ModuleNotFoundError: No module named 'infocore'`
- ❌ `ModuleNotFoundError: No module named 'jobs'`
- ❌ Database lock errors
- ❌ Service crashes/restarts

### 9. Health Check ✅

```bash
# API health
curl http://localhost:8000/api/health

# Should return JSON with:
# - status: "healthy"
# - database: "connected"
# - processor: "initialized"

# Queue stats
curl http://localhost:8000/api/queue-stats

# Cache stats
curl http://localhost:8000/api/stats
```

### 10. Test Search ✅

```bash
# Test zipcode search
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "94301"}'

# Should return Palo Alto meetings
```

### 11. Monitor Memory ✅

```bash
# Watch for memory leaks
watch -n 5 'free -m'

# Check process memory
ps aux --sort=-%mem | head -10

# Expected:
# - API: ~100-200MB
# - Daemon: ~200-400MB (idle), ~600MB (processing)
```

---

## Rollback Plan (If Needed)

If something breaks:

```bash
# Stop services
systemctl stop engagic-api engagic-daemon

# Revert code
cd /root/engagic
git log -5  # Find previous commit hash
git reset --hard <previous-commit-hash>

# Restore old systemd files (if you backed them up)
# OR manually edit back to old paths

# Restore database if corrupted
cp /root/engagic/data/engagic.db.pre-reorganization-backup /root/engagic/data/engagic.db

# Reload and restart
systemctl daemon-reload
systemctl start engagic-api engagic-daemon
```

---

## Post-Migration Verification

### Functional Tests

- [ ] API `/api/health` returns healthy
- [ ] Zipcode search works (`94301`)
- [ ] City search works (`Palo Alto, CA`)
- [ ] State search works (`CA`)
- [ ] Queue processing is active
- [ ] Background sync runs without errors
- [ ] Memory usage stable (<800MB total)

### Log Checks

```bash
# Check for import errors (should be none)
journalctl -u engagic-api --since "10 minutes ago" | grep "ModuleNotFoundError"
journalctl -u engagic-daemon --since "10 minutes ago" | grep "ModuleNotFoundError"

# Check for successful processing
journalctl -u engagic-daemon --since "10 minutes ago" | grep "SUCCESS"

# Check for adapter errors
journalctl -u engagic-daemon --since "10 minutes ago" | grep "FAILED"
```

### Database Verification

```bash
# Count meetings
sqlite3 /root/engagic/data/engagic.db "SELECT COUNT(*) FROM meetings;"

# Count cities
sqlite3 /root/engagic/data/engagic.db "SELECT COUNT(*) FROM cities;"

# Check queue
sqlite3 /root/engagic/data/engagic.db "SELECT COUNT(*) FROM job_queue WHERE status='pending';"

# Verify no corruption
sqlite3 /root/engagic/data/engagic.db "PRAGMA integrity_check;"
```

---

## Known Issues & Solutions

### Issue: Import errors after pull

**Symptom:** `ModuleNotFoundError: No module named 'infocore'`

**Solution:**
```bash
# Check git status
cd /root/engagic
git status

# Ensure old directories are deleted
ls -la | grep infocore  # Should return nothing

# Force clean
git clean -fd
git pull
```

### Issue: Services won't start

**Symptom:** Services fail to start or crash immediately

**Solution:**
```bash
# Check detailed logs
journalctl -u engagic-api -n 100 --no-pager
journalctl -u engagic-daemon -n 100 --no-pager

# Common fixes:
# 1. Systemd paths not updated
# 2. Missing .env file
# 3. Database locked (another process)
```

### Issue: High memory usage

**Symptom:** Memory climbs above 1.5GB

**Solution:**
```bash
# Restart daemon (clears memory)
systemctl restart engagic-daemon

# Monitor during processing
watch -n 2 'ps aux | grep python'

# Check for memory leaks in logs
journalctl -u engagic-daemon | grep "\[Memory\]"
```

---

## Success Criteria

✅ **Migration successful if:**

1. Both services running (`systemctl status` shows active)
2. No import errors in logs
3. API health check returns healthy
4. Search endpoints work
5. Background sync processing meetings
6. Memory usage stable (<800MB)
7. Database integrity check passes

---

## Cleanup (After Successful Migration)

After 24-48 hours of stable operation:

```bash
# Remove old backup (if everything works)
rm /root/engagic/data/engagic.db.pre-reorganization-backup

# Keep daily backups running (cron job should continue)
```

---

## Support Commands

Quick reference for troubleshooting:

```bash
# Service status
systemctl status engagic-api engagic-daemon

# Restart everything
systemctl restart engagic-api engagic-daemon

# View logs
journalctl -u engagic-api -f
journalctl -u engagic-daemon -f

# Check imports
python3 -c "from server.main import app; print('OK')"

# Memory usage
free -m

# Disk usage
df -h /root/engagic

# Database size
ls -lh /root/engagic/data/engagic.db
```

---

## Notes

- **Import paths changed:** `infocore.*` → new structure
- **No schema changes:** Database structure unchanged
- **No data migration:** Existing data works as-is
- **Systemd services:** Only paths changed, logic same
- **Zero downtime:** Not possible, plan for ~5 min maintenance window

---

**Good luck! The structure is cleaner, the code is simpler, and the future is bright.** 🚀

**Questions?** Check logs first, then review docs/REORGANIZATION_2025.md
