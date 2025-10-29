# SmokePAC / SpikeWatch - The Confrontational Layer

**Status:** Schizo ramblings, future project
**Last Updated:** 2025-01-29

---

## The Problem

Meeting summaries are nice. But they're polishing shit.

**The real question isn't "what's being discussed" - it's "who paid for this decision?"**

- Your local councilmember votes for a development
- That developer donated $50K to their campaign last year
- Nobody connects the dots
- Democracy theater continues

**The data exists but is intentionally fragmented:**
- Federal campaign finance: OpenSecrets has it
- State campaign finance: 50 different APIs, varying disclosure quality
- Local campaign finance: Often paper records, county clerk offices, FOIA requests
- Some just don't declare. "Undisclosed millions" from family dynasties.

**Example:** CA State Assembly rep, several million in donations, website says "undisclosed". Family dynasty. No way to see who's paying her.

---

## The Vision

**Engagic:** Neutral data layer. What's being discussed.

**SmokePAC/SpikeWatch:** Confrontational layer. Who paid for it.

**Connection layer:** "This zoning vote benefits Developer X who donated $50K to Councilmember Y last quarter."

### Architecture

```
engagic (infocore)
  ↓ meetings, agendas, votes, motions

smokepac (corruption layer)
  ↓ campaign finance, donations, lobbyists

connection engine
  ↓ map decisions to money
  ↓ expose patterns
  ↓ track repeat offenders
```

---

## Data Sources

### Campaign Finance (Scrapers Needed)

**Federal:**
- OpenSecrets API (already exists)
- FEC data (bulk downloads)

**State (50 different systems):**
- California: Cal-Access API (but has "undisclosed" loopholes)
- New York: NYSBOE
- Texas: TEC
- Florida: Florida Division of Elections
- etc. (each state is different, some are dogshit)

**Local (the hard part):**
- City clerk offices (often paper records)
- County election boards
- FOIA requests
- Sometimes no disclosure requirements at all

### Meeting Data (From Engagic)

**Already have:**
- Meeting agendas and summaries
- Agenda items with topics

**Need to scrape:**
- Vote records (who voted how on what)
- Motion data (who proposed, who seconded)
- Public comment names (who shows up, which side)

**Storage:**
```sql
CREATE TABLE votes (
    id TEXT PRIMARY KEY,
    meeting_id TEXT,
    agenda_item_id TEXT,
    councilmember_name TEXT,
    vote TEXT, -- yes/no/abstain
    motion_type TEXT -- approve/deny/table
);

CREATE TABLE motions (
    id TEXT PRIMARY KEY,
    agenda_item_id TEXT,
    proposer TEXT,
    seconder TEXT,
    outcome TEXT
);
```

---

## Features

### 1. Donor-Decision Mapping

**Show the money:**
- "Councilmember Smith voted YES on this development"
- "Developer X donated $25,000 to Smith in 2024"
- "Smith voted YES on 3 other Developer X projects this year"

**Timeline view:**
- Donation → Vote → Development approval
- Make the corruption visual and obvious

### 2. NIMBY/Developer Tracker

**Who shows up and why:**
- Parse public comment names from meetings
- Track who opposes what (housing, density, transit)
- Cross-reference with property ownership records
- Expose: "These 5 people oppose every housing project. 3 are landlords."

**Developer patterns:**
- Which developers lobby which councilmembers
- Success rates per developer
- Donation amounts vs. project approvals

### 3. Voting Patterns

**Councilmember profiles:**
- How do they vote on zoning/housing/police/budget?
- Who donates to them?
- Which developers benefit from their votes?
- Attendance record (do they even show up?)

**Bloc analysis:**
- Which councilmembers vote together?
- Common donors across voting blocs?
- Follow the money through voting coalitions

### 4. Red Flags

**Automatic detection:**
- Vote within 90 days of large donation
- Multiple votes benefiting same donor
- Undisclosed conflicts of interest
- Abstentions (why? financial interest?)

---

## Why Separate from Engagic?

**Engagic stays neutral:**
- Just the data: meetings, agendas, summaries
- No judgment, no politics
- Open source, trustworthy
- "Free of guilt"

**SmokePAC is confrontational:**
- Exposing corruption
- Making accusations
- Could face legal threats
- Needs editorial oversight

**They need each other:**
- SmokePAC needs Engagic's meeting data (votes, motions, decisions)
- Engagic needs SmokePAC to actually make a difference (not just polish shit)

**Architecture:**
- Engagic: Public database, open API
- SmokePAC: Separate DB, pulls from Engagic API
- Connection layer: Maps money to decisions

---

## Challenges

### Technical

**Data quality:**
- State APIs are inconsistent
- Local data often doesn't exist
- Name matching (John Smith the donor = John Smith the councilmember?)
- Temporal alignment (when did donation happen vs. vote?)

**Scale:**
- 50 state campaign finance systems
- Thousands of local jurisdictions
- Different disclosure rules everywhere
- Some data is paper-only

### Legal

**Libel risk:**
- "Councilmember X is corrupt" = lawsuit
- Need to present facts, let users draw conclusions
- "X voted for Y's project after receiving Z donation" = fact

**FOIA costs:**
- Local records often require formal requests
- Some jurisdictions charge fees
- Time-consuming, doesn't scale

### Ethical

**Privacy concerns:**
- Public officials = fair game
- Regular citizens at meetings = trickier
- Donors = public record, but still

**False positives:**
- Donation doesn't prove corruption
- Sometimes votes align with donations for legitimate reasons
- Need nuance, not witch hunts

---

## MVP Scope

Start small, prove value:

### Phase 1: Single City Pilot (e.g., Palo Alto, CA)

**Data:**
- Get Engagic vote data (from meeting minutes/videos)
- Scrape CA campaign finance for city councilmembers
- Manual FOIA for local donations if needed

**Features:**
- Simple list: "Councilmember X received $Y from Z"
- Timeline: Donations → Votes
- Search: "Who donated to this councilmember?"

### Phase 2: Pattern Detection

**Add:**
- Vote tracking: How did each councilmember vote?
- Developer tracking: Which developers benefit?
- Red flags: Vote within 90 days of donation

### Phase 3: Scale to 10 Cities

**Pick cities with:**
- Good Engagic coverage
- Accessible campaign finance data
- Active development/housing debates

---

## Naming

**Options:**
- **SmokePAC** - "expose the smoke-filled rooms"
- **SpikeWatch** - "spiking the narrative"
- **ClearCorrupt** - too on the nose?
- **FollowTheMoney** - already taken
- **VoteTrace** - boring but descriptive

**Vibe:** Confrontational but factual. Not a conspiracy site. Citations for everything.

---

## Why This Matters

**Meeting summaries are necessary but insufficient.**

Citizens need to know:
1. What's being discussed (Engagic)
2. Who benefits from the decision (SmokePAC)
3. Who paid for that outcome (SmokePAC)

**The goal:**
- Make corruption obvious and visible
- Give citizens the tools to hold officials accountable
- Turn "they're all corrupt" cynicism into "here's the specific corruption, let's fix it"

**The risk:**
- Engagic is nice. SmokePAC is dangerous.
- Could face legal threats, pressure, intimidation
- Need to be bulletproof on facts and sourcing

**The alternative:**
- Keep polishing the shit
- Democracy theater continues
- Nothing changes

---

## Next Steps (Way Future)

1. Finish Engagic userland features first (profiles, alerts, digests)
2. Add vote/motion scraping to Engagic (neutral data layer)
3. Pilot SmokePAC with single city (Palo Alto?)
4. Prove value before scaling
5. Figure out legal structure (nonprofit? Journalism shield?)

**For now:** Keep building Engagic. Let it be useful and neutral. When it's stable, then we can expose the rot.

---

**"Sunlight is the best disinfectant." - Louis Brandeis**

Let's actually shine the light, not just polish the surface.
