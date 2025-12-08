# Deliberation - Civic Opinion Clustering

Structured public input on legislative matters with opinion clustering, consensus detection, and trust-based moderation.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  FRONTEND (SvelteKit)                                                       │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  /deliberate/[matter_id]     Dedicated deliberation page                ││
│  │  ├── +page.server.ts         Loads matter + existing deliberation       ││
│  │  └── +page.svelte            JIT creation, panel rendering              ││
│  │                                                                         ││
│  │  /lib/components/deliberation/                                          ││
│  │  ├── DeliberationPanel.svelte  Main container (tabs, stats, submit)     ││
│  │  ├── CommentCard.svelte        Vote buttons, consensus badge            ││
│  │  └── ClusterViz.svelte         2D scatter plot of opinion groups        ││
│  │                                                                         ││
│  │  /lib/api/deliberation.ts      API client (15 functions)                ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  BACKEND (FastAPI)                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  server/routes/deliberation.py  (428 lines)                             ││
│  │  ├── GET  /api/v1/deliberations/{id}           Public: get state        ││
│  │  ├── GET  /api/v1/deliberations/{id}/results   Public: clustering       ││
│  │  ├── GET  /api/v1/deliberations/matter/{id}    Public: by matter        ││
│  │  ├── POST /api/v1/deliberations                Auth: create             ││
│  │  ├── POST /api/v1/deliberations/{id}/comments  Auth: submit comment     ││
│  │  ├── POST /api/v1/deliberations/{id}/votes     Auth: vote               ││
│  │  ├── GET  /api/v1/deliberations/{id}/my-votes  Auth: user's votes       ││
│  │  ├── GET  /api/v1/deliberations/{id}/pending   Admin: moderation queue  ││
│  │  ├── POST /api/v1/deliberations/{id}/moderate  Admin: approve/reject    ││
│  │  └── POST /api/v1/deliberations/{id}/compute   Admin: run clustering    ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  DATABASE (PostgreSQL)                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  database/repositories_async/deliberation.py  (738 lines)               ││
│  │                                                                         ││
│  │  Tables:                                                                ││
│  │  ├── deliberations              One per matter, links to city_matters   ││
│  │  ├── deliberation_participants  Pseudonymous tracking (Participant 1)   ││
│  │  ├── deliberation_comments      User submissions, mod_status field      ││
│  │  ├── deliberation_votes         Agree/disagree/pass per comment         ││
│  │  ├── deliberation_results       Cached clustering output (JSONB)        ││
│  │  └── userland.deliberation_trusted_users  Auto-approval registry        ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  CLUSTERING (This module)                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  deliberation/clustering.py  (289 lines)                                ││
│  │  ├── PCA dimensionality reduction to 2D                                 ││
│  │  ├── K-means clustering (dynamic K)                                     ││
│  │  ├── Laplace-smoothed consensus detection                               ││
│  │  └── Per-group vote tallies                                             ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

**Total:** ~2,500 lines across all layers

---

## Module Structure

```
deliberation/
├── __init__.py      # 15 lines - Module exports, CONSENSUS_THRESHOLD
└── clustering.py    # 289 lines - PCA + k-means + consensus

Total: 304 lines
```

---

## Clustering Algorithm

### Input

```python
vote_matrix: np.ndarray  # Shape: (n_participants, n_comments)
                         # Values: -1 (disagree), 0 (pass), 1 (agree), NaN (unvoted)
user_ids: List[str]      # User IDs corresponding to rows
comment_ids: List[int]   # Comment IDs corresponding to columns
```

### Processing

1. **Impute missing votes:** Replace NaN with column mean
2. **PCA to 2D:** Project for visualization
3. **Determine K:** `K = min(5, 2 + n_participants // 12)`
4. **K-means:** Group by voting similarity
5. **Consensus:** Laplace-smoothed agreement probability

### Dynamic K

```
K = min(5, 2 + floor(n_participants / 12))

12 participants  -> K = 3
24 participants  -> K = 4
60+ participants -> K = 5 (capped)
```

### Consensus Score

```python
P(agree | cluster) = (agrees + 1) / (total + 2)  # Laplace smoothing
consensus = mean(P(agree) for each cluster)
```

- **>0.8:** High consensus (all groups agree)
- **<0.5:** Low consensus (groups disagree)

### Output

```python
{
    "positions": [[x, y], ...],           # 2D per participant
    "clusters": {user_id: cluster_id},    # Cluster assignment
    "cluster_centers": [[x, y], ...],     # Centroid per cluster
    "consensus": {comment_id: score},     # 0-1 per comment
    "group_votes": {                      # Per-cluster tallies
        cluster_id: {
            comment_id: {"A": agrees, "D": disagrees, "S": seen}
        }
    },
    "k": int,
    "n_participants": int,
    "n_comments": int
}
```

Returns `None` if <3 participants or <2 comments.

---

## Trust-Based Moderation

```
User submits comment
    │
    ▼
[is_user_trusted(user_id)?]
    │
    ├── YES: mod_status = 1 (approved, visible immediately)
    │
    └── NO: mod_status = 0 (pending moderation)
            │
            ▼
        [Admin reviews]
            │
            ├── APPROVE: mod_status = 1, mark_user_trusted()
            └── REJECT: mod_status = -1 (hidden)
```

**First approval grants permanent trust.** Subsequent comments auto-approve.

---

## Admin Moderation CLI

```bash
# List all pending comments
./deploy.sh moderate

# Interactive review
./deploy.sh moderate review <deliberation_id>

# Direct actions
python scripts/moderate.py approve <comment_id>
python scripts/moderate.py reject <comment_id>
```

---

## Frontend Routes

### `/deliberate/[matter_id]`

Dedicated deliberation page, separate from matter detail page.

**Page load:**
1. Fetch matter info
2. Check for existing deliberation
3. If exists: render DeliberationPanel
4. If not: show "Start Discussion" button (creates JIT on click)

**Components:**
- **DeliberationPanel:** Two tabs (Vote on Comments, Opinion Groups)
- **CommentCard:** Agree/Pass/Disagree buttons, consensus badge
- **ClusterViz:** 2D scatter plot with group legend

### Entry Points

1. **AgendaItem:** Purple "Deliberate" button (shows when item has matter_id)
2. **Matter page:** "Join Community Discussion" CTA link

---

## API Reference

### Public (no auth)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/deliberations/{id}` | State + approved comments |
| GET | `/api/v1/deliberations/{id}/results` | Clustering visualization data |
| GET | `/api/v1/deliberations/matter/{matter_id}` | Active deliberation for matter |

### Authenticated

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/deliberations` | Create deliberation |
| POST | `/api/v1/deliberations/{id}/comments` | Submit comment (10-500 chars) |
| POST | `/api/v1/deliberations/{id}/votes` | Vote: 1=agree, 0=pass, -1=disagree |
| GET | `/api/v1/deliberations/{id}/my-votes` | Current user's votes |

### Admin (Bearer token)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/deliberations/{id}/pending` | Moderation queue |
| POST | `/api/v1/deliberations/{id}/moderate` | Approve/reject comment |
| POST | `/api/v1/deliberations/{id}/compute` | Trigger clustering |

---

## Database Schema

```sql
-- Deliberation sessions (one per matter)
CREATE TABLE deliberations (
    id TEXT PRIMARY KEY,               -- delib_{matter_id}_{hash}
    matter_id TEXT NOT NULL REFERENCES city_matters(id),
    banana TEXT NOT NULL,
    topic TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP,
    closed_at TIMESTAMP
);

-- Pseudonymous participants
CREATE TABLE deliberation_participants (
    deliberation_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    participant_number INTEGER NOT NULL,  -- "Participant 1", etc.
    created_at TIMESTAMP,
    PRIMARY KEY (deliberation_id, user_id)
);

-- Comments with moderation status
CREATE TABLE deliberation_comments (
    id SERIAL PRIMARY KEY,
    deliberation_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    participant_number INTEGER NOT NULL,
    txt TEXT NOT NULL,
    mod_status INTEGER DEFAULT 0,  -- -1=hidden, 0=pending, 1=approved
    created_at TIMESTAMP,
    UNIQUE (deliberation_id, user_id, txt)
);

-- Votes on comments
CREATE TABLE deliberation_votes (
    comment_id INTEGER NOT NULL REFERENCES deliberation_comments(id),
    user_id TEXT NOT NULL,
    vote INTEGER NOT NULL,  -- -1, 0, 1
    created_at TIMESTAMP,
    PRIMARY KEY (comment_id, user_id)
);

-- Cached clustering results
CREATE TABLE deliberation_results (
    deliberation_id TEXT PRIMARY KEY,
    n_participants INTEGER,
    n_comments INTEGER,
    k INTEGER,
    positions JSONB,
    clusters JSONB,
    cluster_centers JSONB,
    consensus JSONB,
    group_votes JSONB,
    computed_at TIMESTAMP
);

-- Trust registry (in userland schema)
CREATE TABLE userland.deliberation_trusted_users (
    user_id TEXT PRIMARY KEY,
    first_approved_at TIMESTAMP
);
```

---

## Usage

```python
import numpy as np
from deliberation import compute_deliberation_clusters, CONSENSUS_THRESHOLD

vote_matrix = np.array([
    [ 1,  1, -1, np.nan],
    [ 1,  1, -1, 0],
    [-1, -1,  1, 1],
    [-1, -1,  1, 1],
])

user_ids = ["user_a", "user_b", "user_c", "user_d"]
comment_ids = [101, 102, 103, 104]

results = compute_deliberation_clusters(vote_matrix, user_ids, comment_ids)

if results:
    consensus_comments = [
        cid for cid, score in results["consensus"].items()
        if score >= CONSENSUS_THRESHOLD
    ]
```

---

## Edge Cases

| Condition | Behavior |
|-----------|----------|
| < 3 participants | Returns `None` |
| < 2 comments | Returns `None` |
| All identical votes | PCA returns zeros |
| All NaN in column | Imputes to 0.0 |
| Fewer participants than K | Adjusts K down |

---

## Constants

```python
CONSENSUS_THRESHOLD = 0.8  # Score above which comment is consensus
```

---

## Related Files

| File | Lines | Purpose |
|------|-------|---------|
| `deliberation/clustering.py` | 289 | PCA + k-means algorithm |
| `database/repositories_async/deliberation.py` | 738 | PostgreSQL persistence |
| `server/routes/deliberation.py` | 428 | API endpoints |
| `frontend/src/lib/api/deliberation.ts` | 306 | API client |
| `frontend/src/lib/components/deliberation/*.svelte` | ~850 | UI components |
| `frontend/src/routes/deliberate/[matter_id]/*` | ~150 | Dedicated page |
| `scripts/moderate.py` | 160 | Admin CLI |
| `docs/DELIBERATION_LOCAL_FIRST.md` | 400 | PWA implementation plan |

---

## Future: Local-First PWA

See `docs/DELIBERATION_LOCAL_FIRST.md` for planned offline support:
- IndexedDB for local state
- Background Sync for queued comments/votes
- Optimistic UI with sync indicators

---

**Last Updated:** 2025-12-07
