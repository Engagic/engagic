"""Create jurisdictions for selfhosted registry entries that don't have one yet.

The registry (data/selfhosted_sites.json) is the one place a
self-hosted body is described: its pages for the adapter, and under
"jurisdiction" its name, state, type and optional vernacular for the banana.
This only inserts missing rows; existing jurisdictions are never modified, so
a frozen banana stays frozen if the registry entry is later edited.

    uv run scripts/onboard_selfhosted.py            # plan
    uv run scripts/onboard_selfhosted.py --apply
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db_postgres import Database
from database.models import Jurisdiction
from scripts._jurisdiction_naming import make_banana
from vendors.adapters.custom.selfhosted_adapter_async import load_sites


async def main(apply: bool) -> None:
    db = await Database.create()
    try:
        async with db.pool.acquire() as conn:
            existing = {r["slug"]: r["banana"] for r in await conn.fetch(
                "SELECT slug, banana FROM jurisdictions WHERE vendor = 'selfhosted'")}
        for slug, site in load_sites().items():
            meta = site.get("jurisdiction")
            if not meta:
                print(f"skip {slug}: no jurisdiction block")
                continue
            if slug in existing:
                print(f"have {existing[slug]:<32} {slug}")
                continue
            banana = make_banana(meta["name"], meta["state"], meta.get("vernacular"))
            row = Jurisdiction(banana=banana, name=meta["name"], state=meta["state"], vendor="selfhosted",
                               slug=slug, type=meta["type"], status="active", population=meta.get("population"))
            if await db.jurisdictions.get_city(banana):
                print(f"COLLISION {banana} already exists for another source; not adding {slug}")
                continue
            print(f"{'add ' if apply else 'plan'} {banana:<32} {meta['type']:<22} {meta['name']}")
            if apply:
                await db.jurisdictions.add_city(row)
    finally:
        await db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args().apply))
