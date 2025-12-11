#!/bin/bash
# Happening This Week Analysis Runner
#
# Runs Claude Code autonomously to analyze upcoming agenda items
# and populate the happening_items table.
#
# Usage:
#   ./scripts/run_happening.sh
#
# Cron example (run twice daily at 6am and 6pm):
#   0 6,18 * * * /opt/engagic/scripts/run_happening.sh >> /var/log/engagic/happening.log 2>&1

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Load environment if not already set
if [ -z "$DATABASE_URL" ]; then
    if [ -f .env ]; then
        export $(grep -v '^#' .env | xargs)
    fi
fi

# Verify database connection
if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL not set"
    exit 1
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') Starting Happening This Week analysis..."

# Run Claude Code with the happening prompt
# --allowedTools restricts to Bash for database queries only
claude -p "$(cat prompts/happening.md)" --allowedTools "Bash(psql:*)"

echo "$(date '+%Y-%m-%d %H:%M:%S') Happening analysis complete"
