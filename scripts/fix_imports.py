#!/usr/bin/env python3
"""
Fix imports in scripts after refactor
"""
import re
from pathlib import Path

REPLACEMENTS = [
    # config
    (r'from infocore\.config import config', 'from config import config'),
    (r'from infocore\.config import Config', 'from config import Config'),

    # database
    (r'from infocore\.database\.unified_db import UnifiedDatabase', 'from database.db import UnifiedDatabase'),
    (r'from infocore\.database import DatabaseManager', 'from database.db import DatabaseManager'),
    (r'from infocore\.database\.database_manager import DatabaseManager', 'from database.db import DatabaseManager'),

    # processing/pipeline
    (r'from infocore\.processing\.processor import AgendaProcessor', 'from pipeline.processor import AgendaProcessor'),
    (r'from infocore\.processing\.topic_normalizer import TopicNormalizer', 'from analysis.topics.normalizer import TopicNormalizer'),

    # adapters
    (r'from infocore\.adapters\.all_adapters import', 'from vendors.adapters.all_adapters import'),
    (r'from infocore\.adapters\.civicclerk_adapter import', 'from vendors.adapters.civicclerk_adapter import'),
    (r'from infocore\.adapters\.civicplus_adapter import', 'from vendors.adapters.civicplus_adapter import'),
    (r'from infocore\.adapters\.granicus_adapter import', 'from vendors.adapters.granicus_adapter import'),
    (r'from infocore\.adapters\.legistar_adapter import', 'from vendors.adapters.legistar_adapter import'),
    (r'from infocore\.adapters\.novusagenda_adapter import', 'from vendors.adapters.novusagenda_adapter import'),
    (r'from infocore\.adapters\.primegov_adapter import', 'from vendors.adapters.primegov_adapter import'),
]

def fix_file(filepath):
    """Fix imports in a single file"""
    with open(filepath, 'r') as f:
        content = f.read()

    original = content
    for pattern, replacement in REPLACEMENTS:
        content = re.sub(pattern, replacement, content)

    if content != original:
        with open(filepath, 'w') as f:
            f.write(content)
        return True
    return False

def main():
    scripts_dir = Path(__file__).parent
    fixed = 0

    for script in scripts_dir.glob("*.py"):
        if script.name == "fix_imports.py":
            continue

        if fix_file(script):
            print(f"Fixed: {script.name}")
            fixed += 1

    print(f"\nTotal files fixed: {fixed}")

if __name__ == "__main__":
    main()
