"""Scoring and display selection for keymap helper entries.

The scoring algorithm surfaces shortcuts that are actively being learned:
used recently, but not yet mastered.  Score formula::

    score = recency × learning × (1 - mastery × 0.95)

- **recency** — decays exponentially from 1.0 as days since last use grows.
- **learning** — rises with ``count``, caps at 1.0 after ~10 uses.
- **mastery** — rises when both ``count`` and ``age`` satisfy the configured
  thresholds simultaneously; suppresses the score toward zero.
"""

import math
import time

from . import _log
from ..storage import store


# Number of modifiers used to sort the display list.
_MODIFIERS: frozenset[str] = frozenset({"ALT", "CTRL", "SHIFT"})


def compute_score(entry: dict, now: float, prefs: object) -> float:
    """Compute the learning score for a single store entry.

    Higher scores mean the shortcut is more worth showing right now.
    A score near zero means it is either too new, too old, or mastered.

    Args:
        entry: Dict with ``count``, ``ema``, ``last_used``, ``first_used``.
        now: Current Unix timestamp.
        prefs: Addon preferences object with ``mastery_count``,
            ``mastery_age_days`` attributes.

    Returns:
        A float score >= 0.0.
    """
    count: int = entry.get("count", 0)
    last_used: float = entry.get("last_used", 0.0)
    first_used: float = entry.get("first_used", now)

    # Recency: 1.0 if used today, decays to ~0.05 over 90 days.
    days_since = (now - last_used) / 86400.0
    recency = math.exp(-days_since / 30.0)

    # Learning: rises with count, caps at 1.0 after ~10 uses.
    learning = min(1.0, count / 10.0)

    # Mastery: rises when both count and age satisfy the thresholds.
    age_days = (now - first_used) / 86400.0
    mastery_count: int = getattr(prefs, "mastery_count", 20)
    mastery_age: int = getattr(prefs, "mastery_age_days", 14)
    mastery = min(
        1.0,
        (count / mastery_count) * (age_days / mastery_age),
    )

    return recency * learning * (1.0 - mastery * 0.95)


def _display_sort_key(combo: str) -> tuple[int, str]:
    """Return a sort key for stable, readable display ordering.

    Bare keys (``G``, ``R``) sort before single-modifier combos
    (``CTRL+A``), which sort before multi-modifier combos
    (``CTRL+SHIFT+A``).  Within each group entries are sorted
    alphabetically by the key name.

    Args:
        combo: Canonical combo string, e.g. ``"CTRL+SHIFT+A"``.

    Returns:
        A ``(modifier_count, key_name)`` tuple suitable for ``sorted()``.
    """
    parts = combo.split("+")
    mod_count = sum(1 for p in parts if p in _MODIFIERS)
    key_name = parts[-1]
    return (mod_count, key_name)


def get_display_entries(
    context_key: str,
    prefs: object,
    resolver: object,
) -> list[tuple[str, str]]:
    """Return the scored, filtered, and sorted entries for the overlay.

    Selects the top ``prefs.max_entries`` entries by score, then sorts
    the selection by ``(modifier_count, key_name)`` for stable display.

    Args:
        context_key: Current context key, e.g. ``"VIEW_3D#OBJECT#WINDOW"``.
        prefs: Addon preferences with ``max_entries``, ``mastery_count``,
            ``mastery_age_days`` attributes.
        resolver: Module or object with a ``resolve_combo(combo, area)``
            callable, used to fetch display names.

    Returns:
        List of ``(combo, display_name)`` tuples, ready to render.
    """
    now = time.time()
    max_entries: int = getattr(prefs, "max_entries", 10)

    scored: list[tuple[float, str]] = []
    for combo, entry in store.all_entries(context_key):
        score = compute_score(entry, now, prefs)
        if score > 0.0:
            scored.append((score, combo))

    scored.sort(reverse=True)
    top = scored[:max_entries]

    # Build a lightweight area substitute so resolve_combo can filter keymaps
    # by space_type without needing a real bpy.types.Area object.
    space_type = context_key.split("#")[0] if context_key else ""

    class _FakeArea:
        type = space_type

    fake_area = _FakeArea()

    result: list[tuple[str, str]] = []
    for _score, combo in top:
        resolved = resolver.resolve_combo(combo, fake_area)
        display_name = resolved[1] if resolved else combo
        result.append((combo, display_name))

    result.sort(key=lambda item: _display_sort_key(item[0]))
    _log(f"scorer: {len(result)} entries for {context_key!r}")
    return result


def cleanup_stale(prefs: object) -> None:
    """Remove stale entries from all contexts in the store.

    Two classifiers:

    - **Noise** — ``count < 3`` and ``last_used`` older than 30 days.
      Accidental or one-off presses that were never meaningfully learned.
    - **Abandoned** — ``last_used`` older than ``prefs.cleanup_abandoned_days``.
      Not used in a very long time; start fresh if the user returns.

    Args:
        prefs: Addon preferences with ``cleanup_abandoned_days`` attribute.
    """
    now = time.time()
    noise_threshold = 30 * 86400.0
    abandoned_days: int = getattr(prefs, "cleanup_abandoned_days", 365)
    abandoned_threshold = abandoned_days * 86400.0

    removed = 0
    for context_key, combo, entry in _iter_all_entries():
        last_used: float = entry.get("last_used", 0.0)
        count: int = entry.get("count", 0)
        age = now - last_used

        if age > abandoned_threshold:
            store.delete_entry(context_key, combo)
            removed += 1
        elif count < 3 and age > noise_threshold:
            store.delete_entry(context_key, combo)
            removed += 1

    if removed:
        _log(f"scorer: removed {removed} stale entries")


def _iter_all_entries() -> list[tuple[str, str, dict]]:
    """Collect all ``(context_key, combo, entry)`` triples from the store.

    Materialises the iteration into a list so that the store can be
    mutated during ``cleanup_stale`` without modifying a live iterator.

    Returns:
        List of ``(context_key, combo, entry)`` triples.
    """
    # Access the internal store data directly to iterate all contexts.
    # pylint: disable=protected-access
    rows: list[tuple[str, str, dict]] = []
    from ..storage.store import _data
    for context_key, combos in _data.get("contexts", {}).items():
        for combo, entry in list(combos.items()):
            rows.append((context_key, combo, entry))
    return rows
