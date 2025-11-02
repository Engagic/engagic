# No Daemon Architecture

**Date**: November 2, 2025
**Status**: Active - Daemon mode completely removed

## Why We Removed The Daemon

The daemon coupled syncing + processing which was **dangerous** for production:

❌ **Old (Dangerous):**
```bash
./deploy.sh start daemon
# Automatically syncs ALL 825 cities
# Automatically processes ALL queued meetings
# No control, no visibility, costs unpredictable
```

✅ **New (Explicit Control):**
```bash
./deploy.sh sync-cities @regions/bay-area.txt    # Fetch only (free)
./deploy.sh preview-queue                         # Review queue
./deploy.sh process-cities @regions/bay-area.txt  # Process only what you want ($)
```

## What Was Removed

1. **`start_daemon()`** - No longer exists
2. **`stop_daemon()`** - Replaced with `kill_background_processes()`
3. **`restart_daemon()`** - Removed entirely
4. **`logs-daemon`** - Removed (manual processes don't log consistently)
5. **`daemon-status`** - Removed (replaced with `status` showing background processes)
6. **Systemd service** - No longer created/managed

## Current Architecture

### API Server (Systemd)
```bash
./deploy.sh start    # Start API (systemd service)
./deploy.sh stop     # Stop API + kill background processes
./deploy.sh restart  # Restart API
./deploy.sh status   # Show API + background processes
```

### Data Operations (Manual/Cron)
```bash
# Single city
./deploy.sh sync-city paloaltoCA
./deploy.sh process-cities paloaltoCA

# Multiple cities (regional)
./deploy.sh sync-cities @regions/bay-area.txt
./deploy.sh process-cities @regions/bay-area.txt

# Batch
./deploy.sh process-unprocessed
```

### Safety Mechanisms
```bash
./deploy.sh kill-background    # Kill any running background jobs
./deploy.sh preview-queue      # Check queue before processing
./deploy.sh extract-text ID    # Test extraction without LLM costs
```

## Migration from Daemon

If you were using daemon mode:

**Before:**
```bash
./deploy.sh start daemon  # Automatic sync + process
```

**After:**
```bash
# Set up cron jobs (recommended)
# In crontab -e:
0 2 * * * /root/engagic/deploy.sh sync-cities @regions/prod.txt
0 3 * * * /root/engagic/deploy.sh process-unprocessed

# Or run manually:
./deploy.sh sync-cities @regions/bay-area.txt
./deploy.sh process-cities @regions/bay-area.txt
```

## Future: Dedicated Sync/Process Cron Jobs

**Phase 7 (Planned):**
- Per-user cron job management
- Scheduled sync windows (off-peak hours)
- Scheduled processing with cost limits
- Email notifications for completion/failures
- Queue monitoring and alerts

**Example:**
```bash
./deploy.sh schedule-sync @regions/bay-area.txt --time "2:00 AM" --days "Mon,Wed,Fri"
./deploy.sh schedule-process --limit 100 --max-cost 10.00 --notify email@example.com
```

## Commands Reference

### Service Management
```bash
start                     # Start API service
stop                      # Stop API + kill background processes
restart                   # Restart API service
status                    # Show system status
logs-api                  # Show API logs
kill-background           # Kill any running background processes
```

### Data Operations
```bash
# Single city
sync-city BANANA          # Fetch meetings (enqueue)
sync-and-process BANANA   # Fetch + process immediately

# Multiple cities
sync-cities CITIES        # Fetch multiple (comma-separated or @file)
process-cities CITIES     # Process queued jobs for multiple cities
sync-and-process-cities   # Fetch + process multiple cities

# Batch
process-unprocessed       # Process all unprocessed meetings in queue

# Preview
preview-queue [CITY]      # Show queued jobs (no processing)
extract-text ID [FILE]    # Extract PDF text (no LLM, manual review)
```

## Safety Best Practices

1. **Always preview before processing:**
   ```bash
   ./deploy.sh sync-cities @regions/new.txt
   ./deploy.sh preview-queue
   # Review what's queued before...
   ./deploy.sh process-cities @regions/new.txt
   ```

2. **Test extraction quality:**
   ```bash
   ./deploy.sh extract-text MEETING_ID /tmp/check.txt
   less /tmp/check.txt  # Verify quality before burning API credits
   ```

3. **Start small:**
   ```bash
   ./deploy.sh sync-and-process-cities @regions/test-small.txt  # 2 cities, ~$0.02
   ```

4. **Monitor costs:**
   - Monolithic (PDF-only): ~$0.02/meeting
   - Item-level (HTML agenda): ~$0.01/meeting (50% savings)
   - Always check queue size before processing: `./deploy.sh preview-queue`

5. **Kill runaway processes:**
   ```bash
   ./deploy.sh kill-background  # Immediately stops all background processing
   ```

## Files Modified

- `deploy.sh` - Removed all daemon code, ~200 lines deleted
- `CLAUDE.md` - Updated to reflect explicit control architecture
- `docs/REGIONAL_PROCESSING.md` - Updated workflows
- Created `docs/NO_DAEMON.md` - This file

## Legacy Cleanup

If you have old daemon service installed:

```bash
# Stop and disable old service
sudo systemctl stop engagic-daemon
sudo systemctl disable engagic-daemon
sudo rm /etc/systemd/system/engagic-daemon.service
sudo systemctl daemon-reload

# Kill any orphaned processes
./deploy.sh kill-background
```
