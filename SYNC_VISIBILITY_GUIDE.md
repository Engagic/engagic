# Sync Visibility Guide

## What You'll See When Running Sync

When you run `./deploy.sh sync-cities @regions/metro-areas-working.txt`, you'll now see detailed, structured logging for every aspect of the sync process.

---

## Log Output Format

All logs use scannable tags in brackets:
- `[Sync]` - City sync progress
- `[Vendor]` - Vendor adapter method (API vs HTML)
- `[Items]` - Agenda item processing
- `[Matters]` - Legislative matter tracking
- `[Queue]` - Processing queue operations

---

## Example Sync Output

### 1. City Sync Start
```
[Sync] Starting nashvilleTN (legistar)
[Vendor] legistar:Nashville using API
[Vendor] legistar:Nashville API returned 5 meetings
```

### 2. Meeting Discovery
```
[Sync] nashvilleTN: Found 5 meetings, 173 items (40 with matter tracking)
[Sync] nashvilleTN: Breakdown: 5 item-level, 5 with HTML agenda, 5 with PDF packet
[Sync] nashvilleTN: Storing 5 meetings...
```

### 3. Item Processing (The Symphony!)
```
[Items] RS2025-1600 - Ryan White HIV/AIDS Program funding | Matter: RS2025-1600
[Items] BL2025-1106 - Community garden zoning ordinance | Matter: BL2025-1106
[Items] Procedural (skipped): Approval of Minutes from November 4
[Items] Procedural (skipped): Public Comment Period
[Items] BL2025-1098 - Affordable housing development at 123 Main St | Matter: BL2025-1098
[Items] RS2025-1601 - Metro Parks capital improvements
```

### 4. Matter Tracking
```
[Matters] New: RS2025-1600 (Resolution) - 3 sponsors
[Matters] Duplicate: BL2025-1106 (Ordinance)
[Matters] New: BL2025-1098 (Ordinance) - 5 sponsors
[Items] Stored 173 items (22 procedural, 0 with preserved summaries)
```

### 5. Sync Complete
```
[Sync] nashvilleTN: Progress 5/5 meetings
[Sync] nashvilleTN: Complete! 5 meetings, 173 items, 38 matters tracked (2.3s)
```

---

## What Each Log Shows

### [Sync] Tags
- **Starting**: City name, vendor
- **Found**: Meeting count, item count, matter count
- **Breakdown**: Item-level vs monolithic
- **Progress**: Every 10 meetings
- **Complete**: Summary with timing

### [Vendor] Tags
- **Method used**: API or HTML
- **Success**: Number of meetings returned
- **Fallback**: When API fails, shows HTML fallback

### [Items] Tags
- **Each item**: Title (truncated to 50 chars)
- **Matter tracking**: Shows matter_file or matter_id
- **Procedural**: Items skipped for processing
- **Summary**: Total stored, procedural count, preserved summaries

### [Matters] Tags
- **New**: First time seeing this matter (bill/resolution)
- **Duplicate**: Matter seen before (cross-meeting tracking)
- **Details**: Matter type, sponsor count

---

## Full Example: Los Angeles Sync

```bash
[Sync] Starting losangelesCA (primegov)
[Vendor] primegov:lacity using HTML (no API available)
[Sync] losangelesCA: Found 3 meetings, 71 items (71 with matter tracking)
[Sync] losangelesCA: Breakdown: 3 item-level, 3 with HTML agenda, 0 with PDF packet
[Sync] losangelesCA: Storing 3 meetings...

# First meeting
[Items] Motion - CD 12 street resurfacing project | Matter: 24-1234
[Items] Ordinance - Affordable housing incentive program | Matter: 24-1235
[Items] CF 24-0500 - Budget allocation for parks department | Matter: CF 24-0500
[Items] Procedural (skipped): Communications from the Mayor
[Items] Procedural (skipped): Public Comment

[Matters] New: 24-1234 (CD 12) - 0 sponsors
[Matters] New: 24-1235 (Ordinance) - 2 sponsors
[Matters] Duplicate: CF 24-0500 (City File)
[Items] Stored 71 items (5 procedural, 0 with preserved summaries)

[Sync] losangelesCA: Complete! 3 meetings, 71 items, 69 matters tracked (1.8s)
```

---

## What You'll Notice

### The Symphony of Everything Working Together

1. **Vendor Intelligence**: See exactly which method works (API first, HTML fallback)
2. **Item Discovery**: Watch items flow from vendor to database
3. **Matter Tracking**: See duplicates detected across meetings (same bill in multiple committees)
4. **Procedural Filtering**: See noise items get skipped (roll call, minutes, public comment)
5. **Substantive Items**: See important legislation with matter tracking
6. **Performance**: City sync timing shows bottlenecks

### Duplicate Detection Example

```
# Meeting 1 (City Council)
[Matters] New: BL2025-1106 (Ordinance) - 3 sponsors

# Meeting 2 (Planning Commission - 2 weeks later)
[Matters] Duplicate: BL2025-1106 (Ordinance)

# Meeting 3 (Budget Committee - 1 month later)
[Matters] Duplicate: BL2025-1106 (Ordinance)
```

This shows BL2025-1106 moving through the legislative process across 3 meetings!

---

## Log Filtering

### Watch specific aspects:

```bash
# See only sync progress
./deploy.sh sync-cities @regions/metro-areas-working.txt | grep "\\[Sync\\]"

# See only vendor methods (API vs HTML)
./deploy.sh sync-cities @regions/metro-areas-working.txt | grep "\\[Vendor\\]"

# See only items (the main show)
./deploy.sh sync-cities @regions/metro-areas-working.txt | grep "\\[Items\\]"

# See only matter tracking
./deploy.sh sync-cities @regions/metro-areas-working.txt | grep "\\[Matters\\]"

# See procedural items being skipped
./deploy.sh sync-cities @regions/metro-areas-working.txt | grep "Procedural"

# See errors only
./deploy.sh sync-cities @regions/metro-areas-working.txt | grep -i error
```

### Watch live with color:

```bash
# Follow sync in real-time
tail -f /root/engagic/engagic.log | grep --color=auto "\\[Sync\\]\\|\\[Items\\]\\|\\[Matters\\]"
```

---

## Performance Insights

### What timing tells you:

- **< 1s**: City with few meetings (5-10)
- **1-3s**: Normal city (10-20 meetings)
- **3-10s**: Large city (20-50 meetings) or slow vendor
- **> 10s**: Very large city (50+ meetings) or network issues

### Rate limiting visibility:

```
[Sync] nashvilleTN: Complete! (2.3s)
[RateLimit] Waiting 3.5s before next vendor request
[Sync] Starting austinTX (legistar)
```

---

## Troubleshooting

### No items found:
```
[Sync] cityname: Found 5 meetings, 0 items (0 with matter tracking)
[Sync] cityname: Breakdown: 0 item-level, 0 with HTML agenda, 5 with PDF packet
```
**Meaning**: Monolithic fallback (packet PDF only)

### All items procedural:
```
[Items] Procedural (skipped): Roll Call
[Items] Procedural (skipped): Invocation
[Items] Procedural (skipped): Approval of Minutes
[Items] Stored 3 items (3 procedural, 0 with preserved summaries)
```
**Meaning**: No substantive items in this meeting (ceremony only)

### Vendor fallback:
```
[Vendor] legistar:cityname API failed (HTTP 403), falling back to HTML scraping
[Vendor] legistar:cityname using HTML fallback
```
**Meaning**: API auth failed, HTML works fine

---

## Expected Output for Metro Areas

Based on `regions/metro-areas-working.txt` (18 cities):

- **San Francisco**: ~20 meetings, ~100 items, ~80 with matter tracking
- **Palo Alto**: ~10 meetings, ~44 items, ~44 with matter tracking (PrimeGov)
- **Dallas**: ~15 meetings, ~60 items, ~60 with matter tracking
- **Austin**: ~12 meetings, ~44 items, ~44 with matter tracking
- **Denver**: ~18 meetings, ~72 items, ~72 with matter tracking
- **Boston**: ~8 meetings, ~15 items, ~15 with matter tracking
- **Nashville**: ~5 meetings, ~12 items, ~12 with matter tracking

**Total expected**: ~150 meetings, ~500 items, ~400 with matter tracking

**Time**: ~30-60 seconds (with rate limiting)

---

## What Success Looks Like

```
[Sync] Starting sanfranciscoCA (legistar)
[Vendor] legistar:sf using API
[Vendor] legistar:sf API returned 20 meetings
[Sync] sanfranciscoCA: Found 20 meetings, 105 items (85 with matter tracking)
[Sync] sanfranciscoCA: Breakdown: 20 item-level, 20 with HTML agenda, 20 with PDF packet

[Items] BL2025-245 - Housing ordinance for affordable development | Matter: BL2025-245
[Items] RS2025-189 - Climate action plan funding allocation | Matter: RS2025-189
[Items] Procedural (skipped): Public Comment
[Items] BL2025-246 - Transit expansion proposal | Matter: BL2025-246

[Matters] New: BL2025-245 (Ordinance) - 4 sponsors
[Matters] New: RS2025-189 (Resolution) - 2 sponsors
[Matters] Duplicate: BL2025-246 (Ordinance)
[Items] Stored 105 items (8 procedural, 0 with preserved summaries)

[Sync] sanfranciscoCA: Complete! 20 meetings, 105 items, 83 matters tracked (3.2s)
```

---

**Generated**: 2025-11-11
**Status**: Ready for big sync with full visibility
**Tags**: [Sync], [Vendor], [Items], [Matters], [Queue]
