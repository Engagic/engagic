#!/usr/bin/env python3
"""Fix import paths after migration to new structure"""
import os
import re
from pathlib import Path

def fix_imports_in_file(filepath):
    """Fix import statements in a Python file"""
    with open(filepath, 'r') as f:
        content = f.read()
    
    original = content
    
    # Map old imports to new imports based on file location
    file_path = Path(filepath)
    
    # Determine how many levels up to go from current file
    if 'backend/core' in str(file_path):
        # In core module
        content = content.replace('from config import', 'from backend.core.config import')
        content = content.replace('from utils import', 'from backend.core.utils import')
        content = content.replace('from fullstack import', 'from backend.core.processor import')
        content = content.replace('from databases import', 'from backend.database import')
        content = content.replace('from databases.database_manager import', 'from backend.database.database_manager import')
        content = content.replace('from adapters import', 'from backend.adapters.all_adapters import')
    
    elif 'backend/api' in str(file_path):
        # In api module  
        content = content.replace('from config import', 'from backend.core.config import')
        content = content.replace('from utils import', 'from backend.core.utils import')
        content = content.replace('from fullstack import', 'from backend.core.processor import')
        content = content.replace('from databases import', 'from backend.database import')
        content = content.replace('from databases.database_manager import', 'from backend.database.database_manager import')
        content = content.replace('from adapters import', 'from backend.adapters.all_adapters import')
        
    elif 'backend/services' in str(file_path):
        # In services module
        content = content.replace('from config import', 'from backend.core.config import')
        content = content.replace('from utils import', 'from backend.core.utils import')
        content = content.replace('from fullstack import', 'from backend.core.processor import')
        content = content.replace('from databases import', 'from backend.database import')
        content = content.replace('from databases.database_manager import', 'from backend.database.database_manager import')
        content = content.replace('from adapters import', 'from backend.adapters.all_adapters import')
        
    elif 'backend/database' in str(file_path):
        # In database module
        content = content.replace('from config import', 'from backend.core.config import')
        content = content.replace('from utils import', 'from backend.core.utils import')
        
    elif 'backend/adapters' in str(file_path):
        # In adapters module
        content = content.replace('from pdf_scraper_utils import', 'from backend.adapters.pdf_utils import')
        
    if content != original:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"✓ Fixed imports in {filepath}")
        return True
    return False

# Fix all Python files in backend/
fixed_count = 0
for root, dirs, files in os.walk('backend'):
    for file in files:
        if file.endswith('.py') and file != '__init__.py':
            filepath = os.path.join(root, file)
            if fix_imports_in_file(filepath):
                fixed_count += 1

print(f"\nFixed imports in {fixed_count} files")
