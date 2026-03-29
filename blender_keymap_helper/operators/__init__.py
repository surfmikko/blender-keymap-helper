"""Operators: modal key tracker, toggle, and reset to defaults."""

import bpy

from . import commands, modal_tracker  # noqa: F401
from ..core import _log

_addon_keymaps: list = []


def _start_tracker() -> None:
    """Invoke the tracker operator if a window context is available."""
    try:
        bpy.ops.keymap_helper.start_tracker("INVOKE_DEFAULT")
        _log("operators: tracker started")
    except Exception as exc:
        _log(f"operators: failed to start tracker: {exc}")


def _on_load_post(*_args: object) -> None:
    """Start the tracker after a file has loaded."""
    _start_tracker()


def register() -> None:
    """Register operator classes, keymaps, watchdog, and load_post handler."""
    bpy.utils.register_class(modal_tracker.CheatsheetTrackerOperator)
    bpy.utils.register_class(commands.CheatsheetToggleOperator)
    bpy.utils.register_class(commands.CheatsheetClearMemoryOperator)
    bpy.utils.register_class(commands.CheatsheetResetOperator)
    _register_keymaps()
    bpy.app.handlers.load_post.append(_on_load_post)
    bpy.app.timers.register(
        modal_tracker.watchdog, first_interval=5.0, persistent=True
    )
    _start_tracker()


def unregister() -> None:
    """Unregister operator classes, keymaps, watchdog, and load_post handler."""
    if bpy.app.timers.is_registered(modal_tracker.watchdog):
        bpy.app.timers.unregister(modal_tracker.watchdog)
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
    _unregister_keymaps()
    bpy.utils.unregister_class(commands.CheatsheetResetOperator)
    bpy.utils.unregister_class(commands.CheatsheetClearMemoryOperator)
    bpy.utils.unregister_class(commands.CheatsheetToggleOperator)
    bpy.utils.unregister_class(modal_tracker.CheatsheetTrackerOperator)


def _register_keymaps() -> None:
    """Register default shortcuts in the 3D View keymap.

    - Ctrl+Shift+H  — toggle overlay visibility
    - Ctrl+Shift+Del — clear all recorded usage data
    """
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
        kmi = km.keymap_items.new(
            "keymap_helper.toggle",
            type="H",
            value="PRESS",
            ctrl=True,
            shift=True,
        )
        _addon_keymaps.append((km, kmi))
        kmi = km.keymap_items.new(
            "keymap_helper.clear_memory",
            type="DEL",
            value="PRESS",
            ctrl=True,
            shift=True,
        )
        _addon_keymaps.append((km, kmi))


def _unregister_keymaps() -> None:
    """Remove all registered addon keymaps."""
    for km, kmi in _addon_keymaps:
        km.keymap_items.remove(kmi)
    _addon_keymaps.clear()
