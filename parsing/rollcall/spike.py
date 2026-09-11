"""Roll-call parser access for the minutes route.

The parser itself is still the validated 2026-08-04 spike at
scripts/spikes/rollcall/parse.py (gazetteer, per-dialect template drivers,
publish gate). It is loaded from there rather than copied so there is one
implementation while drivers are added; promotion into this package is the
next step once a third dialect lands.
"""

import importlib.util
import sys
from pathlib import Path
from typing import Any, Optional

SPIKE_PARSE = Path(__file__).resolve().parent.parent.parent / "scripts" / "spikes" / "rollcall" / "parse.py"

# banana -> dialect driver name in the spike's PARSERS table. Coverage grows
# one driver at a time; a city without a row is reported, never guessed.
DIALECTS = {
    "milwaukeeWI": "milwaukee",
    "denverCO": "denver",
}


def load_spike_parser():
    spec = importlib.util.spec_from_file_location("rollcall_parse", SPIKE_PARSE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load roll-call parser from {SPIKE_PARSE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["rollcall_parse"] = module
    spec.loader.exec_module(module)
    return module


def norm_file(dialect: str, value: Any) -> Optional[str]:
    """Normalize a file number the way each dialect prints it (Milwaukee: digits only)."""
    if not value:
        return None
    text = str(value).strip()
    if dialect == "milwaukee":
        return "".join(ch for ch in text if ch.isdigit()) or None
    return text
