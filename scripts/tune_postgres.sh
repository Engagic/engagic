#!/bin/bash
#
# PostgreSQL Tuning Script for 2GB VPS
#
# Optimizes PostgreSQL configuration for engagic deployment on a 2GB RAM VPS.
# Based on industry best practices for small VPS deployments.
#
# Usage:
#     sudo ./scripts/tune_postgres.sh
#
# This script:
# 1. Backs up current postgresql.conf
# 2. Applies performance tuning parameters
# 3. Enables slow query logging
# 4. Restarts PostgreSQL
#
# Resources:
# - https://pgtune.leopard.in.ua/ (PGTune)
# - https://wiki.postgresql.org/wiki/Tuning_Your_PostgreSQL_Server

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PG_VERSION="16"  # Adjust if different
PGCONF="/etc/postgresql/${PG_VERSION}/main/postgresql.conf"
BACKUP_SUFFIX=".backup.$(date +%Y%m%d_%H%M%S)"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}ERROR: This script must be run as root (use sudo)${NC}"
    exit 1
fi

# Check if PostgreSQL config exists
if [ ! -f "$PGCONF" ]; then
    echo -e "${RED}ERROR: PostgreSQL config not found at $PGCONF${NC}"
    echo "Adjust PG_VERSION in script or check PostgreSQL installation"
    exit 1
fi

echo -e "${GREEN}PostgreSQL Tuning Script for 2GB VPS${NC}"
echo "========================================"
echo ""
echo "Config file: $PGCONF"
echo "Backup will be created: ${PGCONF}${BACKUP_SUFFIX}"
echo ""

# Confirm before proceeding
read -p "Continue with tuning? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# Backup current config
echo -e "${YELLOW}Backing up current configuration...${NC}"
cp "$PGCONF" "${PGCONF}${BACKUP_SUFFIX}"
echo "Backup created: ${PGCONF}${BACKUP_SUFFIX}"

# Apply tuning parameters
echo -e "${YELLOW}Applying performance tuning...${NC}"

# Memory Configuration (2GB VPS)
# shared_buffers: 25% of RAM = 512MB
# effective_cache_size: 75% of RAM = 1536MB
# work_mem: 16MB (for sorts/joins)
# maintenance_work_mem: 128MB (for VACUUM/INDEX)

sed -i "s/^shared_buffers.*/shared_buffers = 512MB/" "$PGCONF"
sed -i "s/^#effective_cache_size.*/effective_cache_size = 1536MB/" "$PGCONF"
sed -i "s/^#work_mem.*/work_mem = 16MB/" "$PGCONF"
sed -i "s/^#maintenance_work_mem.*/maintenance_work_mem = 128MB/" "$PGCONF"

# Connection Settings
# max_connections: 100 (align with asyncpg pool max_size)
sed -i "s/^max_connections.*/max_connections = 100/" "$PGCONF"

# Query Planner
# random_page_cost: 1.1 (SSD-optimized, default is 4.0 for HDD)
sed -i "s/^#random_page_cost.*/random_page_cost = 1.1/" "$PGCONF"

# Write-Ahead Log (WAL)
# wal_buffers: 16MB (for write-heavy workloads)
# checkpoint_completion_target: 0.9 (spread checkpoints over longer time)
sed -i "s/^#wal_buffers.*/wal_buffers = 16MB/" "$PGCONF"
sed -i "s/^#checkpoint_completion_target.*/checkpoint_completion_target = 0.9/" "$PGCONF"

# Logging (Slow Query Tracking)
# logging_collector: on (enable log collection)
# log_min_duration_statement: 1000ms (log queries >1 second)
sed -i "s/^#logging_collector.*/logging_collector = on/" "$PGCONF"
sed -i "s/^#log_min_duration_statement.*/log_min_duration_statement = 1000/" "$PGCONF"

# Statistics
# track_activity_query_size: 2048 (track longer queries)
sed -i "s/^#track_activity_query_size.*/track_activity_query_size = 2048/" "$PGCONF"

echo -e "${GREEN}Tuning parameters applied!${NC}"
echo ""
echo "Applied settings:"
echo "  - shared_buffers = 512MB (25% of RAM)"
echo "  - effective_cache_size = 1536MB (75% of RAM)"
echo "  - work_mem = 16MB"
echo "  - maintenance_work_mem = 128MB"
echo "  - max_connections = 100"
echo "  - random_page_cost = 1.1 (SSD)"
echo "  - wal_buffers = 16MB"
echo "  - checkpoint_completion_target = 0.9"
echo "  - logging_collector = on"
echo "  - log_min_duration_statement = 1000ms"
echo ""

# Restart PostgreSQL
echo -e "${YELLOW}Restarting PostgreSQL...${NC}"
systemctl restart postgresql

# Verify restart
if systemctl is-active --quiet postgresql; then
    echo -e "${GREEN}✅ PostgreSQL restarted successfully${NC}"
else
    echo -e "${RED}❌ ERROR: PostgreSQL failed to restart${NC}"
    echo "Check logs: sudo journalctl -u postgresql -n 50"
    echo "Restore backup if needed: sudo cp ${PGCONF}${BACKUP_SUFFIX} ${PGCONF}"
    exit 1
fi

# Verify connection
echo -e "${YELLOW}Verifying database connection...${NC}"
if su - postgres -c "psql -c 'SELECT version();' engagic" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Database connection successful${NC}"
else
    echo -e "${YELLOW}⚠️  Could not connect to 'engagic' database (may not exist yet)${NC}"
fi

# Show current settings
echo ""
echo -e "${GREEN}Current PostgreSQL Memory Settings:${NC}"
su - postgres -c "psql -c \"SHOW shared_buffers; SHOW effective_cache_size; SHOW work_mem; SHOW maintenance_work_mem;\" engagic" 2>/dev/null || echo "(Database not available for query)"

echo ""
echo -e "${GREEN}✅ PostgreSQL tuning complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Monitor slow queries: sudo tail -f /var/log/postgresql/postgresql-${PG_VERSION}-main.log"
echo "  2. Enable pg_stat_statements: sudo -u postgres psql -c 'CREATE EXTENSION pg_stat_statements;' engagic"
echo "  3. Check active connections: sudo -u postgres psql -c 'SELECT count(*) FROM pg_stat_activity;' engagic"
echo ""
echo "To restore original config:"
echo "  sudo cp ${PGCONF}${BACKUP_SUFFIX} ${PGCONF}"
echo "  sudo systemctl restart postgresql"
