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

- `bay-area.txt` - San Francisco Peninsula + East Bay core cities
- `bay-area-2.txt` - Bay Area smaller cities + counties (Peninsula, East Bay, North Bay, 9 counties)
- `bay-area-all.txt` - Comprehensive Bay Area: all cities and counties across Peninsula/South Bay, East Bay, and North Bay (~120 entries)
- `notable-unprocessed.txt` - Notable cities nationwide not yet onboarded (~63 cities across 25+ states, sorted alphabetically)
- `test-small.txt` - Small test set for validation (2 cities)

### File Purposes

- **bay-area.txt** - Original core set for daily sync
- **bay-area-2.txt** - Expansion wave: smaller municipalities and county-level jurisdictions
- **bay-area-all.txt** - Complete regional coverage including all entries from bay-area.txt and bay-area-2.txt
- **notable-unprocessed.txt** - Backlog of high-value cities to onboard (includes Washington DC, Indianapolis IN, Memphis TN, etc.)
