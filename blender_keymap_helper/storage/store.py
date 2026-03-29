"""In-memory data store and JSON persistence.

The store holds all shortcut usage statistics in a nested dict mirroring
the JSON structure on disk. All reads and writes go through this module;
the JSON file is only touched on load and debounced flush.

Data structure::

    {
        "version": 1,
        "contexts": {
            "VIEW_3D#OBJECT#WINDOW": {
                "G": {
                    "count": 45,
                    "last_used": 1711234567.0,
                    "first_used": 1710000000.0
                }
            }
        }
    }
"""

import json
import time
from pathlib import Path
from typing import Iterator

import bpy

from ..storage import migration
from ..core import _log

_CURRENT_VERSION: int = 1
_FLUSH_INTERVAL: float = 30.0

# In-memory cache populated on load, flushed to disk periodically.
_data: dict = {"version": _CURRENT_VERSION, "contexts": {}}
_dirty: bool = False
_last_flush: float = 0.0

# Incremented on every write operation (upsert, delete, load).
# The draw callback compares against this to detect stale cache.
generation: int = 0


def _data_path() -> Path:
    """Return the path to the JSON data file in Blender's user config directory.

    Returns:
        Absolute path to ``blender_keymap_helper_data.json``.
    """
    return Path(bpy.utils.user_resource("CONFIG")) / "blender_keymap_helper_data.json"


def load() -> None:
    """Load data from disk into the in-memory cache.

    If the file does not exist or contains invalid JSON the store is
    initialised with an empty dataset.  The loaded data is passed through
    the migration layer before use.
    """
    global _data, _dirty, _last_flush

    path = _data_path()
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            _data = migration.migrate(raw)
            _log(f"store: loaded {path}")
        except (json.JSONDecodeError, OSError) as exc:
            _log(f"store: failed to load {path}: {exc}; starting empty")
            _data = {"version": _CURRENT_VERSION, "contexts": {}}
    else:
        _log(f"store: no data file at {path}; starting empty")
        _data = {"version": _CURRENT_VERSION, "contexts": {}}

    _dirty = False
    _last_flush = time.monotonic()
    mark_dirty()  # Bump generation so draw cache refreshes after load.


def save() -> None:
    """Flush the in-memory cache to disk unconditionally.

    Silently ignores errors so that a write failure does not crash Blender.
    """
    global _dirty, _last_flush

    path = _data_path()
    try:
        path.write_text(
            json.dumps(_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        _dirty = False
        _last_flush = time.monotonic()
        _log(f"store: saved {path}")
    except OSError as exc:
        _log(f"store: failed to save {path}: {exc}")


def flush_if_due() -> None:
    """Save to disk if the store is dirty and the flush interval has elapsed.

    Intended to be called from a ``bpy.app.timers`` callback.
    """
    if _dirty and (time.monotonic() - _last_flush) >= _FLUSH_INTERVAL:
        save()


def mark_dirty() -> None:
    """Mark the store as having unsaved changes and increment the generation."""
    global _dirty, generation
    _dirty = True
    generation += 1


def get_entry(context_key: str, combo: str) -> dict | None:
    """Return the stat entry for a combo in a context, or ``None``.

    Args:
        context_key: Context identifier, e.g. ``"VIEW_3D#OBJECT#WINDOW"``.
        combo: Canonical key combo string, e.g. ``"CTRL+A"``.

    Returns:
        A dict with ``count``, ``last_used``, and ``first_used`` keys,
        or ``None`` if the entry does not exist.
    """
    return _data["contexts"].get(context_key, {}).get(combo)


def upsert_entry(context_key: str, combo: str, data: dict) -> None:
    """Create or replace the stat entry for a combo in a context.

    Args:
        context_key: Context identifier, e.g. ``"VIEW_3D#OBJECT#WINDOW"``.
        combo: Canonical key combo string, e.g. ``"CTRL+A"``.
        data: Dict with ``count``, ``last_used``, and ``first_used`` keys.
    """
    if context_key not in _data["contexts"]:
        _data["contexts"][context_key] = {}
    _data["contexts"][context_key][combo] = data
    mark_dirty()


def all_entries(context_key: str) -> Iterator[tuple[str, dict]]:
    """Yield ``(combo, entry)`` pairs for all entries in a context.

    Args:
        context_key: Context identifier, e.g. ``"VIEW_3D#OBJECT#WINDOW"``.

    Yields:
        Tuples of ``(combo_string, entry_dict)``.
    """
    yield from _data["contexts"].get(context_key, {}).items()


def clear_all() -> None:
    """Remove all stored usage data from every context.

    Marks the store dirty so the change is flushed to disk on the next
    flush interval and the draw cache invalidates on the next redraw.
    """
    _data["contexts"].clear()
    mark_dirty()


def delete_entry(context_key: str, combo: str) -> None:
    """Remove a single entry from the store.

    Args:
        context_key: Context identifier.
        combo: Canonical key combo string to remove.
    """
    context = _data["contexts"].get(context_key)
    if context and combo in context:
        del context[combo]
        mark_dirty()
