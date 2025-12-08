# Deliberation: Local-First PWA Implementation

## Why Local-First for Deliberation

Deliberation is the first truly interactive feature in Engagic. Unlike the core app (read-only meeting data), deliberation involves:

- **User-generated content**: Comments, votes
- **Latency sensitivity**: Voting should feel instant
- **Offline composition**: Draft comments at city council meetings with spotty WiFi
- **Simple conflict resolution**: Append-only comments, last-write-wins votes

This makes it an ideal proving ground for local-first architecture before expanding to other features.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser                               │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │ DeliberationPanel│  │   IndexedDB     │  │Service Worker│ │
│  │   (Svelte)      │◄─┤                 │  │              │ │
│  │                 │  │ - deliberations │  │ - Offline    │ │
│  │ Optimistic UI   │  │ - comment_queue │  │ - Cache API  │ │
│  │                 │  │ - vote_queue    │  │ - Bg Sync    │ │
│  └────────┬────────┘  └────────┬────────┘  └──────┬───────┘ │
│           │                    │                   │         │
└───────────┼────────────────────┼───────────────────┼─────────┘
            │                    │                   │
            ▼                    ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│                      Backend API                             │
│  POST /deliberations/{id}/comments                          │
│  POST /deliberations/{id}/votes                             │
│  GET  /deliberations/{id}                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Model

### IndexedDB Schema

```typescript
// Database: engagic-deliberation
// Version: 1

interface DeliberationStore {
  // Key: deliberation_id
  id: string;
  matter_id: string;
  topic: string;
  comments: Comment[];
  my_votes: Record<number, -1 | 0 | 1>;
  stats: { comment_count: number; vote_count: number; participant_count: number };
  cached_at: number; // timestamp
}

interface OutboundComment {
  // Key: auto-increment
  id?: number;
  deliberation_id: string;
  txt: string;
  created_at: number;
  status: 'pending' | 'syncing' | 'failed';
  retry_count: number;
  error?: string;
}

interface OutboundVote {
  // Key: `${deliberation_id}:${comment_id}`
  deliberation_id: string;
  comment_id: number;
  vote: -1 | 0 | 1;
  created_at: number;
  status: 'pending' | 'syncing' | 'failed';
}
```

### Sync Strategy

| Data Type | Direction | Conflict Resolution |
|-----------|-----------|---------------------|
| Comments (others) | Server -> Client | Server authoritative |
| Comments (mine) | Client -> Server | Append-only, no conflicts |
| Votes (mine) | Bidirectional | Last-write-wins by timestamp |
| Clustering results | Server -> Client | Server authoritative |

---

## Implementation Phases

### Phase 1: Service Worker Foundation

```typescript
// frontend/src/service-worker.ts

import { build, files, version } from '$service-worker';

const CACHE_NAME = `engagic-${version}`;

// Cache static assets on install
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll([...build, ...files, '/offline']);
    })
  );
});

// Network-first for API, cache-first for assets
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  if (url.pathname.startsWith('/api/')) {
    // Network first, fall back to showing offline state
    event.respondWith(networkFirst(event.request));
  } else {
    // Cache first for static assets
    event.respondWith(cacheFirst(event.request));
  }
});
```

**Deliverables:**
- [ ] Basic service worker with asset caching
- [ ] Offline fallback page at `/offline`
- [ ] SvelteKit service worker integration

### Phase 2: IndexedDB Layer

```typescript
// frontend/src/lib/stores/deliberation-db.ts

import { openDB, type IDBPDatabase } from 'idb';

const DB_NAME = 'engagic-deliberation';
const DB_VERSION = 1;

export async function getDB(): Promise<IDBPDatabase> {
  return openDB(DB_NAME, DB_VERSION, {
    upgrade(db) {
      // Cached deliberation state
      db.createObjectStore('deliberations', { keyPath: 'id' });

      // Outbound comment queue
      const comments = db.createObjectStore('comment_queue', {
        keyPath: 'id',
        autoIncrement: true
      });
      comments.createIndex('by_status', 'status');
      comments.createIndex('by_deliberation', 'deliberation_id');

      // Outbound vote queue (composite key)
      db.createObjectStore('vote_queue', {
        keyPath: ['deliberation_id', 'comment_id']
      });
    }
  });
}

export async function queueComment(deliberationId: string, txt: string) {
  const db = await getDB();
  await db.add('comment_queue', {
    deliberation_id: deliberationId,
    txt,
    created_at: Date.now(),
    status: 'pending',
    retry_count: 0
  });
}

export async function queueVote(deliberationId: string, commentId: number, vote: -1 | 0 | 1) {
  const db = await getDB();
  await db.put('vote_queue', {
    deliberation_id: deliberationId,
    comment_id: commentId,
    vote,
    created_at: Date.now(),
    status: 'pending'
  });
}
```

**Deliverables:**
- [ ] IndexedDB wrapper with idb library
- [ ] Queue management functions
- [ ] Cache read/write for deliberation state

### Phase 3: Background Sync

```typescript
// In service worker

self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-deliberation') {
    event.waitUntil(syncOutboundQueues());
  }
});

async function syncOutboundQueues() {
  const db = await getDB();

  // Sync pending comments
  const pendingComments = await db.getAllFromIndex('comment_queue', 'by_status', 'pending');
  for (const comment of pendingComments) {
    try {
      await syncComment(comment);
      await db.delete('comment_queue', comment.id);
    } catch (e) {
      await db.put('comment_queue', {
        ...comment,
        status: 'failed',
        retry_count: comment.retry_count + 1,
        error: e.message
      });
    }
  }

  // Sync pending votes
  const pendingVotes = await db.getAll('vote_queue');
  for (const vote of pendingVotes.filter(v => v.status === 'pending')) {
    try {
      await syncVote(vote);
      await db.delete('vote_queue', [vote.deliberation_id, vote.comment_id]);
    } catch (e) {
      await db.put('vote_queue', { ...vote, status: 'failed' });
    }
  }
}
```

**Deliverables:**
- [ ] Background Sync API registration
- [ ] Retry logic with exponential backoff
- [ ] Failed item recovery

### Phase 4: Optimistic UI

```typescript
// frontend/src/lib/components/deliberation/DeliberationPanel.svelte

import { queueComment, queueVote, getPendingComments } from '$lib/stores/deliberation-db';

// Show pending comments with indicator
const pendingComments = $state<OutboundComment[]>([]);

async function handleSubmitComment() {
  const tempId = Date.now();

  // Optimistically add to UI
  pendingComments.push({
    id: tempId,
    deliberation_id: deliberationId,
    txt: newComment,
    created_at: Date.now(),
    status: 'pending'
  });

  // Queue for sync
  await queueComment(deliberationId, newComment);

  // Request background sync
  if ('serviceWorker' in navigator && 'sync' in window.registration) {
    await navigator.serviceWorker.ready;
    await registration.sync.register('sync-deliberation');
  } else {
    // Fallback: immediate sync attempt
    await syncImmediately();
  }

  newComment = '';
}
```

**Deliverables:**
- [ ] Optimistic comment rendering with "pending" badge
- [ ] Optimistic vote state (instant feedback)
- [ ] Queue status indicator ("3 comments waiting to sync")
- [ ] Sync status listener for UI updates

---

## Offline UX

### States to Handle

1. **Online, synced**: Normal operation
2. **Online, syncing**: Show sync indicator
3. **Online, failed**: Show retry button, error message
4. **Offline, cached**: Read-only mode with queue
5. **Offline, no cache**: Show offline page

### Visual Indicators

```svelte
{#if pendingComments.length > 0}
  <div class="sync-status">
    {#if navigator.onLine}
      <span class="syncing">Syncing {pendingComments.length} comments...</span>
    {:else}
      <span class="offline">{pendingComments.length} comments queued (offline)</span>
    {/if}
  </div>
{/if}

{#each pendingComments as pending}
  <CommentCard
    comment={{ ...pending, participant_number: 'You' }}
    isPending={true}
    status={pending.status}
  />
{/each}
```

---

## Dependencies

```bash
npm install idb  # IndexedDB wrapper
```

SvelteKit already supports service workers via `src/service-worker.ts`.

---

## Testing Checklist

- [ ] Submit comment online, verify appears immediately
- [ ] Submit comment, go offline, verify queued
- [ ] Come back online, verify sync completes
- [ ] Vote while offline, verify queued and syncs
- [ ] Kill network mid-sync, verify retry works
- [ ] Clear IndexedDB, verify graceful degradation
- [ ] Test on actual mobile at city council meeting

---

## Admin Moderation Workflow

### Current State

Moderation endpoints exist but no CLI/UI:

```
GET  /api/v1/deliberations/{id}/pending   # List pending comments
POST /api/v1/deliberations/{id}/moderate  # Approve/reject
```

Auth: `Authorization: Bearer $ENGAGIC_ADMIN_TOKEN`

### CLI Script: `scripts/moderate.py`

```python
#!/usr/bin/env python3
"""
Deliberation moderation CLI.

Usage:
  python scripts/moderate.py list              # List all pending across deliberations
  python scripts/moderate.py review <delib_id> # Interactive review for one deliberation
"""

import asyncio
import sys
from database.db_postgres import Database


async def list_pending():
    """List all pending comments across all deliberations."""
    db = await Database.create()
    try:
        pending = await db.deliberation.get_all_pending_comments()
        if not pending:
            print("No pending comments.")
            return

        print(f"\n{'='*60}")
        print(f"PENDING COMMENTS: {len(pending)}")
        print(f"{'='*60}\n")

        for comment in pending:
            print(f"[{comment['deliberation_id'][:20]}...] #{comment['id']}")
            print(f"  Participant {comment['participant_number']}: {comment['txt'][:100]}")
            print()
    finally:
        await db.close()


async def review_deliberation(deliberation_id: str):
    """Interactive review for a single deliberation."""
    db = await Database.create()
    try:
        pending = await db.deliberation.get_pending_comments(deliberation_id)
        if not pending:
            print("No pending comments for this deliberation.")
            return

        print(f"\nReviewing {len(pending)} pending comments...")
        print("Commands: [a]pprove, [r]eject, [s]kip, [q]uit\n")

        for comment in pending:
            print(f"{'='*40}")
            print(f"Comment #{comment['id']} by Participant {comment['participant_number']}")
            print(f"{'='*40}")
            print(f"\n{comment['txt']}\n")

            while True:
                action = input("Action [a/r/s/q]: ").strip().lower()
                if action == 'a':
                    await db.deliberation.moderate_comment(comment['id'], approve=True)
                    print("-> Approved\n")
                    break
                elif action == 'r':
                    await db.deliberation.moderate_comment(comment['id'], approve=False)
                    print("-> Rejected\n")
                    break
                elif action == 's':
                    print("-> Skipped\n")
                    break
                elif action == 'q':
                    print("Quitting.")
                    return
                else:
                    print("Invalid. Use a/r/s/q")
    finally:
        await db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "list":
        asyncio.run(list_pending())
    elif cmd == "review" and len(sys.argv) > 2:
        asyncio.run(review_deliberation(sys.argv[2]))
    else:
        print(__doc__)
        sys.exit(1)
```

### deploy.sh Integration

Add to deploy.sh:

```bash
# Moderation
moderate)
    echo "Deliberation moderation"
    echo ""
    echo "Commands:"
    echo "  ./deploy.sh moderate list              - List all pending comments"
    echo "  ./deploy.sh moderate review <delib_id> - Interactive review"
    echo ""
    if [ -n "$2" ]; then
        python3 scripts/moderate.py "$2" "$3"
    fi
    ;;
```

### Future: Admin Dashboard

Eventually, build a web UI at `/admin/moderate`:
- List pending comments with context
- One-click approve/reject
- Bulk actions
- Trust user checkbox (auto-approve future comments)

For now, CLI is sufficient given low volume.

---

## Migration Path

1. **Phase 1**: Service worker + offline shell (1-2 days)
2. **Phase 2**: IndexedDB + queue management (2-3 days)
3. **Phase 3**: Background sync (1-2 days)
4. **Phase 4**: Optimistic UI integration (2-3 days)
5. **Phase 5**: Polish + testing (2-3 days)

Total: ~2 weeks for full local-first deliberation.

---

## What Stays Server-Only

- **Clustering computation**: Needs full vote matrix, CPU-intensive
- **Moderation queue**: Admin-only access
- **Trust status**: Server determines if user is trusted
- **Deliberation creation**: Requires auth, creates server record

The local-first layer is purely for resilience and UX, not replacing server authority.
