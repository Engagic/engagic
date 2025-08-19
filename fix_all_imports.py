#!/usr/bin/env python3
"""Fix ALL import paths in the entire codebase"""
import os
import re
from pathlib import Path

def fix_script_imports(filepath):
    """Fix imports in script files - add sys.path and update imports"""
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    # Check if sys.path adjustment already exists
    has_sys_path = any('sys.path' in line for line in lines)
    
    new_lines = []
    import_section_done = False
    
    for i, line in enumerate(lines):
        # Add sys.path adjustment after imports if not present
        if not has_sys_path and not import_section_done and line.strip() and not line.startswith('import') and not line.startswith('from'):
            # We've passed the import section
            import_section_done = True
            # Add sys.path adjustment
            new_lines.append('\n# Add parent directory to path for imports\n')
            new_lines.append('import sys\n')
            new_lines.append('from pathlib import Path\n')
            new_lines.append('sys.path.insert(0, str(Path(__file__).parent.parent))\n\n')
            has_sys_path = True
        
        # Fix import statements
        if line.startswith('from '):
            original = line
            line = line.replace('from databases import', 'from backend.database import')
            line = line.replace('from databases.database_manager import', 'from backend.database.database_manager import')
            line = line.replace('from config import', 'from backend.core.config import')
            line = line.replace('from utils import', 'from backend.core.utils import')
            line = line.replace('from fullstack import', 'from backend.core.processor import')
            line = line.replace('from adapters import', 'from backend.adapters.all_adapters import')
            if line != original:
                print(f"  Fixed: {original.strip()} -> {line.strip()}")
        
        new_lines.append(line)
    
    # Write back
    with open(filepath, 'w') as f:
        f.writelines(new_lines)

def fix_test_imports(filepath):
    """Fix imports in test files"""
    with open(filepath, 'r') as f:
        content = f.read()
    
    original = content
    
    # Add sys.path if not present
    if 'sys.path' not in content:
        import_lines = []
        import_lines.append('import sys')
        import_lines.append('from pathlib import Path')
        import_lines.append('sys.path.insert(0, str(Path(__file__).parent.parent))')
        import_lines.append('')
        
        # Find where to insert (after initial imports)
        lines = content.split('\n')
        insert_pos = 0
        for i, line in enumerate(lines):
            if line.strip() and not line.startswith('import') and not line.startswith('from'):
                insert_pos = i
                break
        
        lines.insert(insert_pos, '\n'.join(import_lines))
        content = '\n'.join(lines)
    
    # Fix imports
    content = content.replace('from databases import', 'from backend.database import')
    content = content.replace('from config import', 'from backend.core.config import')
    content = content.replace('from utils import', 'from backend.core.utils import')
    content = content.replace('from fullstack import', 'from backend.core.processor import')
    content = content.replace('from adapters import', 'from backend.adapters.all_adapters import')
    content = content.replace('import adapters', 'from backend import adapters')
    content = content.replace('import fullstack', 'from backend.core import processor as fullstack')
    
    if content != original:
        with open(filepath, 'w') as f:
            f.write(content)
        return True
    return False

print("=== FIXING SCRIPTS ===")
# Fix scripts
for script in Path('scripts').glob('*.py'):
    print(f"\nProcessing {script}...")
    fix_script_imports(script)

print("\n=== FIXING TESTS ===")
# Fix tests
for test in Path('tests').glob('*.py'):
    print(f"\nProcessing {test}...")
    if fix_test_imports(test):
        print(f"  ✓ Fixed imports")
    else:
        print(f"  No changes needed")

print("\n=== CHECKING BACKEND FOR REMAINING ISSUES ===")
# Double-check backend files
issues = []
for root, dirs, files in os.walk('backend'):
    for file in files:
        if file.endswith('.py'):
            filepath = Path(root) / file
            with open(filepath, 'r') as f:
                content = f.read()
            
            # Check for old patterns
            if 'from adapters import' in content and 'from backend' not in content:
                issues.append(f"{filepath}: Still has 'from adapters import'")
            if 'from databases import' in content and 'from backend' not in content:
                issues.append(f"{filepath}: Still has 'from databases import'")
            if 'from config import' in content and 'from backend' not in content:
                issues.append(f"{filepath}: Still has 'from config import'")

if issues:
    print("\nFound issues:")
    for issue in issues:
        print(f"  - {issue}")
else:
    print("\n✓ All backend imports look good!")

print("\nDone!")
