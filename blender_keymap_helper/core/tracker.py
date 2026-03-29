"""Per-keypress usage stat updates."""

import time

from ..storage import store
from . import _log

# Smoothing factor for the exponential moving average of press frequency.
# F_n = (1 - EMA_ALPHA) * F_{n-1} + EMA_ALPHA * f_n
# where f_n = 1.0 on each press.
EMA_ALPHA: float = 0.1


def record_event(context_key: str, combo: str) -> None:
    """Record one use of a shortcut combo in the given context.

    Creates the entry if it does not exist.  Updates ``count``, ``ema``,
    ``last_used``, and ``first_used`` in the store and marks it dirty
    for the next debounced flush.

    Args:
        context_key: Context identifier, e.g. ``"VIEW_3D#OBJECT#WINDOW"``.
        combo: Canonical key combo string, e.g. ``"G"``.
    """
    now = time.time()
    entry = store.get_entry(context_key, combo)

    if entry is None:
        entry = {"count": 0, "ema": 0.0, "last_used": 0.0, "first_used": now}

    entry["count"] += 1
    entry["ema"] = (1.0 - EMA_ALPHA) * entry.get("ema", 0.0) + EMA_ALPHA * 1.0
    entry["last_used"] = now
    if entry["first_used"] == 0.0:
        entry["first_used"] = now

    store.upsert_entry(context_key, combo, entry)
    _log(
        f"tracker: recorded [{context_key}] {combo}"
        f" count={entry['count']} ema={entry['ema']:.3f}"
    )
