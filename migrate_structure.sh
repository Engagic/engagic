#!/bin/bash

# Engagic Directory Structure Migration Script
# Run this on your VPS to safely restructure the project
# Usage: bash migrate_structure.sh

set -e  # Exit on error

echo "================================"
echo "Engagic Structure Migration v1.0"
echo "================================"
echo ""

# Check if we're in the right directory
if [ ! -f "app/app.py" ]; then
    echo "ERROR: Must run from engagic root directory"
    echo "Current directory: $(pwd)"
    exit 1
fi

# Backup check
echo "⚠️  IMPORTANT: This will restructure your project."
echo "Have you backed up your databases and code? (yes/no)"
read -r response
if [ "$response" != "yes" ]; then
    echo "Please backup first:"
    echo "  tar -czf engagic-backup-$(date +%Y%m%d).tar.gz app/ data/ *.db"
    exit 1
fi

echo ""
echo "Phase 1: Creating new directory structure..."
echo "----------------------------------------"

# Create new directories
mkdir -p backend/{core,api,adapters,database,services}
mkdir -p tests scripts docs data/{databases,cache}

echo "✓ Directory structure created"

echo ""
echo "Phase 2: Copying files to new locations..."
echo "----------------------------------------"

# Core files
cp app/fullstack.py backend/core/processor.py
cp app/config.py backend/core/config.py
cp app/utils.py backend/core/utils.py
echo "✓ Core files copied"

# API files
cp app/app.py backend/api/main.py
if [ -f "app/anthropic_rate_limiter.py" ]; then
    cp app/anthropic_rate_limiter.py backend/api/rate_limiter.py
fi
if [ -f "app/rate_limit_handler.py" ]; then
    cp app/rate_limit_handler.py backend/api/rate_limiter.py
fi
echo "✓ API files copied"

# Adapter files
cp app/adapters.py backend/adapters/all_adapters.py
if [ -f "app/pdf_scraper_utils.py" ]; then
    cp app/pdf_scraper_utils.py backend/adapters/pdf_utils.py
fi
echo "✓ Adapter files copied"

# Database layer
if [ -d "app/databases" ]; then
    cp -r app/databases/* backend/database/
    echo "✓ Database layer copied"
fi

# Services
cp app/daemon.py backend/services/daemon.py
cp app/background_processor.py backend/services/background_processor.py
echo "✓ Services copied"

# Requirements
cp app/requirements.txt backend/requirements.txt
echo "✓ Requirements copied"

echo ""
echo "Phase 3: Moving test and utility files..."
echo "----------------------------------------"

# Move test files to tests/
for file in app/*test*.py app/gatest.py; do
    if [ -f "$file" ]; then
        mv "$file" tests/ 2>/dev/null || true
        echo "  Moved $(basename $file) to tests/"
    fi
done

# Move utility scripts
for file in app/db_viewer.py app/pdf_api_processor.py app/pdf_chunker.py app/import_cities.py app/process_city_meetings.py app/cleanup_duplicate_meetings.py app/fix_meetings_schema.py; do
    if [ -f "$file" ]; then
        mv "$file" scripts/ 2>/dev/null || true
        echo "  Moved $(basename $file) to scripts/"
    fi
done

# Move root level scripts
for file in normalize_meeting_dates.py sync_missing_cities.py update_city.py; do
    if [ -f "$file" ]; then
        mv "$file" scripts/ 2>/dev/null || true
        echo "  Moved $file to scripts/"
    fi
done

# Move deployment scripts
if [ -f "deploy.sh" ]; then
    mv deploy.sh scripts/
fi
if [ -f "app/deploy_background_processor.sh" ]; then
    mv app/deploy_background_processor.sh scripts/
fi
echo "✓ Test and utility files moved"

echo ""
echo "Phase 4: Creating backwards-compatible symlinks..."
echo "----------------------------------------"

# Remove old files and create symlinks
cd app/

# Core symlinks
rm -f app.py fullstack.py config.py utils.py daemon.py background_processor.py adapters.py anthropic_rate_limiter.py rate_limit_handler.py pdf_scraper_utils.py 2>/dev/null

ln -sf ../backend/api/main.py app.py
ln -sf ../backend/core/processor.py fullstack.py
ln -sf ../backend/core/config.py config.py
ln -sf ../backend/core/utils.py utils.py
ln -sf ../backend/services/daemon.py daemon.py
ln -sf ../backend/services/background_processor.py background_processor.py
ln -sf ../backend/adapters/all_adapters.py adapters.py

if [ -f "../backend/api/rate_limiter.py" ]; then
    ln -sf ../backend/api/rate_limiter.py anthropic_rate_limiter.py
    ln -sf ../backend/api/rate_limiter.py rate_limit_handler.py
fi
if [ -f "../backend/adapters/pdf_utils.py" ]; then
    ln -sf ../backend/adapters/pdf_utils.py pdf_scraper_utils.py
fi

# Database directory symlink
if [ -d "databases" ]; then
    rm -rf databases
fi
ln -sf ../backend/database databases

cd ..
echo "✓ Symlinks created"

echo ""
echo "Phase 5: Moving database files..."
echo "----------------------------------------"

# Move database files if they exist in app/
if [ -f "app/locations.db" ]; then
    mv app/locations.db data/databases/
    echo "  Moved locations.db to data/databases/"
fi
if [ -f "app/meetings.db" ]; then
    mv app/meetings.db data/databases/
    echo "  Moved meetings.db to data/databases/"
fi

# Move database files if they exist in app/data/
if [ -f "app/data/locations.db" ]; then
    mv app/data/locations.db data/databases/
    echo "  Moved app/data/locations.db to data/databases/"
fi
if [ -f "app/data/meetings.db" ]; then
    mv app/data/meetings.db data/databases/
    echo "  Moved app/data/meetings.db to data/databases/"
fi
if [ -f "app/data/analytics.db" ]; then
    mv app/data/analytics.db data/databases/
    echo "  Moved app/data/analytics.db to data/databases/"
fi

# Create symlinks back to app/data for compatibility
if [ ! -L "app/data" ]; then
    rm -rf app/data 2>/dev/null
    ln -sf ../data/databases app/data
    echo "✓ Database symlink created"
fi

echo ""
echo "Phase 6: Cleaning up root directory..."
echo "----------------------------------------"

# Move documentation
for file in README-DEPLOYMENT.md ANTHROPIC_DOCS.md; do
    if [ -f "$file" ]; then
        mv "$file" docs/ 2>/dev/null || true
        echo "  Moved $file to docs/"
    fi
done

# Move data files
for file in granicus_view_ids.json app/granicus_view_ids.json app/discovered_cities.json; do
    if [ -f "$file" ]; then
        mv "$file" data/ 2>/dev/null || true
        echo "  Moved $(basename $file) to data/"
    fi
done

echo "✓ Root directory cleaned"

echo ""
echo "Phase 7: Creating __init__.py files..."
echo "----------------------------------------"

# Create __init__.py files for Python packages
touch backend/__init__.py
touch backend/core/__init__.py
touch backend/api/__init__.py
touch backend/adapters/__init__.py
touch backend/database/__init__.py
touch backend/services/__init__.py
touch tests/__init__.py

echo "✓ Python package files created"

echo ""
echo "Phase 8: Testing imports..."
echo "----------------------------------------"

# Test that Python can still import the main modules
python3 -c "import sys; sys.path.insert(0, 'app'); import app" 2>/dev/null && echo "✓ app.py imports correctly" || echo "⚠ app.py import failed"
python3 -c "import sys; sys.path.insert(0, 'app'); import fullstack" 2>/dev/null && echo "✓ fullstack.py imports correctly" || echo "⚠ fullstack.py import failed"
python3 -c "import sys; sys.path.insert(0, 'app'); import daemon" 2>/dev/null && echo "✓ daemon.py imports correctly" || echo "⚠ daemon.py import failed"

echo ""
echo "================================"
echo "Migration Complete!"
echo "================================"
echo ""
echo "Next steps:"
echo "1. Test the API: python app/app.py"
echo "2. Test the daemon: python app/daemon.py --status"
echo "3. If everything works, restart your services:"
echo "   sudo systemctl restart engagic-api"
echo "   sudo systemctl restart engagic-daemon"
echo "4. Monitor logs: tail -f app/engagic.log"
echo ""
echo "To rollback if needed:"
echo "  tar -xzf engagic-backup-YYYYMMDD.tar.gz"
echo ""
echo "New structure:"
echo "  backend/     - All Python backend code"
echo "  tests/       - All test files"
echo "  scripts/     - Utility and deployment scripts"
echo "  docs/        - Documentation"
echo "  data/        - Databases and data files"
echo "  frontend/    - SvelteKit frontend (unchanged)"
echo "  app/         - Symlinks for backwards compatibility"