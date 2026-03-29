"""Storage layer: JSON persistence and in-memory cache."""

import bpy

from . import migration, store  # noqa: F401
from .store import flush_if_due, load, save
from ..core import _log


def _on_load_pre(*_args: object) -> None:
    """Flush to disk before a new file is loaded."""
    _log("storage: load_pre — flushing")
    save()


def _on_save_pre(*_args: object) -> None:
    """Flush to disk before the blend file is saved."""
    _log("storage: save_pre — flushing")
    save()


def _timer_flush() -> float:
    """Periodic timer callback that flushes the store if due.

    Returns:
        Seconds until the next call.
    """
    flush_if_due()
    return 30.0


def register() -> None:
    """Register storage handlers and load data from disk."""
    _log("storage: register")
    load()
    bpy.app.handlers.load_pre.append(_on_load_pre)
    bpy.app.handlers.save_pre.append(_on_save_pre)
    bpy.app.timers.register(_timer_flush, first_interval=30.0, persistent=True)


def unregister() -> None:
    """Save data to disk and unregister storage handlers."""
    _log("storage: unregister — flushing")
    save()
    if _on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_on_load_pre)
    if _on_save_pre in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(_on_save_pre)
    if bpy.app.timers.is_registered(_timer_flush):
        bpy.app.timers.unregister(_timer_flush)
