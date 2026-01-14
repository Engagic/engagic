# Regional City Lists

This directory contains curated lists of cities for regional analysis.

## Usage

Process cities from a region file:
```bash
./deploy.sh sync-cities @regions/bay-area.txt
./deploy.sh process-cities @regions/bay-area.txt
./deploy.sh sync-and-process-cities @regions/bay-area.txt
```

Or use comma-separated list directly:
```bash
./deploy.sh sync-cities 'paloaltoCA,oaklandCA,berkeleyCA'
```

## File Format

- One city banana per line
- Comments start with `#`
- Blank lines are ignored

Example:
```
# Bay Area cities
paloaltoCA
oaklandCA
berkeleyCA
```

## Regional Intelligence Layer

These regional lists are designed for:
1. **Regional analysis** - Identify patterns across municipalities
2. **Comparative studies** - Compare how different cities handle similar issues
3. **Intelligence layer testing** - Process multiple cities for critical analysis
4. **Demo purposes** - Show regional civic engagement patterns

## Available Regions

- `bay-area.txt` - San Francisco Peninsula + East Bay (12 cities)
- `test-small.txt` - Small test set for validation (2 cities)

Add more regions as needed!
