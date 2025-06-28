# Database Population System

This system replaces the inefficient "just-in-time" city registration with comprehensive pre-population of all US cities.

## Quick Start

```bash
cd app
python run_population.py
```

Choose option 1 for a quick start with priority cities, or option 3 for a test run.

## Files Overview

- **`run_population.py`** - User-friendly population script with menu options
- **`batch_populate.py`** - Core batch processing system with parallel/sequential options
- **`vendor_detector.py`** - Advanced vendor discovery using search queries
- **`populate_cities.py`** - Original population script (legacy)

## How It Works

1. **City Data**: Uses `uszipcode` library to get all US cities with population > 1000
2. **Vendor Discovery**: Searches Google for "{city} {state} city council" to find government websites
3. **Pattern Matching**: Detects vendor platforms (PrimeGov, Legistar, etc.) from URLs
4. **Slug Extraction**: Extracts city_slug from subdomain patterns like `cityname.primegov.com`
5. **Database Storage**: Stores comprehensive city data in the `cities` table

## Usage Options

### Test Run (5 cities)
```bash
python run_population.py --test
```

### Priority Cities Only
```bash
python batch_populate.py --no-vendors  # Fast, no vendor discovery
```

### Full Population
```bash
python batch_populate.py  # All cities with vendor discovery (takes hours)
```

### Update Missing Vendors
```bash
python populate_cities.py --update-vendors
```

## API Changes

The search endpoints now use the pre-populated database instead of creating entries on-demand:

- `GET /api/search/{query}` - Returns 404 if city not in database
- No more "We're adding your city" messages
- Instant results for all pre-populated cities

## Database Schema

Cities are stored in the `cities` table with:
- `city_name`, `state` - Official city/state names
- `city_slug` - URL-friendly identifier (often matches vendor subdomain)
- `vendor` - Platform provider (primegov, legistar, etc.)
- `primary_zipcode` - Main zipcode for the city
- `zipcodes` - JSON array of all zipcodes in the city
- `county` - County name

## Vendor Detection

The system recognizes these vendor patterns:

- **PrimeGov**: `cityname.primegov.com` (confidence: 95%)
- **Legistar**: `cityname.legistar.com` (confidence: 90%)
- **CivicPlus**: `cityname.civicplus.com` (confidence: 85%)
- **Granicus**: `cityname.granicus.com` (confidence: 85%)
- **Direct**: `cityname.gov/.org/.us` (confidence: 60%)

## Performance

- **Sequential**: ~2-3 cities per minute (more reliable)
- **Parallel**: ~5-10 cities per minute (faster but may hit rate limits)
- **Full Population**: ~6,000 cities = 2-4 hours depending on vendor discovery

## Rate Limiting

- 1.5 second delay between search requests
- User-Agent rotation to avoid blocking
- Automatic retry logic for failed requests

## Error Handling

- Continues processing if individual cities fail
- Comprehensive logging of errors and successes
- Progress reports every 25-50 cities
- Final statistics summary