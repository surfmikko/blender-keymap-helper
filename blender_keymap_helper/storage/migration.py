"""Data format version migration.

Each version bump adds a migration step below.  ``migrate()`` walks the
version chain so data from any prior version is always brought current.
"""

from ..core import _log

_CURRENT_VERSION: int = 1


def migrate(data: dict) -> dict:
    """Migrate a loaded data dict to the current format version.

    Applies all necessary migration steps in order.  If the data already
    matches the current version it is returned unchanged.

    Args:
        data: Raw dict loaded from the JSON data file.

    Returns:
        The migrated data dict, ready for use by the store.
    """
    version = data.get("version", 0)

    if version < 1:
        _log(f"migration: v{version} → v1")
        data = _migrate_to_v1(data)

    data["version"] = _CURRENT_VERSION
    return data


def _migrate_to_v1(data: dict) -> dict:
    """Migrate pre-v1 data to v1 format.

    Ensures all entries have the ``ema`` field.  Entries that only have
    ``count`` get ``ema`` seeded from count via a rough approximation.

    Args:
        data: Raw data dict without a version field.

    Returns:
        Data dict conforming to v1 schema.
    """
    contexts = data.get("contexts", {})
    for combos in contexts.values():
        for entry in combos.values():
            if "ema" not in entry:
                # Approximate EMA from existing count: treat each press as
                # having contributed EMA_ALPHA = 0.1 cumulatively.
                count = entry.get("count", 0)
                entry["ema"] = 1.0 - (0.9 ** count) if count > 0 else 0.0
    return {"version": 1, "contexts": contexts}
