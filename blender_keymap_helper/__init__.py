"""Blender Keymap Helper — viewport overlay that surfaces keyboard shortcuts worth learning.

Tracks usage statistics per shortcut per context and displays the shortcuts
most relevant to the user's current learning stage.
"""

bl_info = {
    "name": "Blender Keymap Helper",
    "description": (
        "Shortcut learning tool: tracks usage and surfaces the shortcuts "
        "most worth learning for the current editor context."
    ),
    "version": (1, 0, 0),
    "blender": (5, 1, 0),
    "location": "View3D › Overlay corner",
    "category": "3D View",
    "support": "COMMUNITY",
}

# Canonical addon package name — works for both direct install and extensions.
# Submodules import this instead of reconstructing it from __package__.
ADDON_PACKAGE: str = __package__

from . import core, storage, overlay, operators, preferences


def register() -> None:
    """Register all addon classes and handlers."""
    preferences.register()
    storage.register()
    core.register()
    overlay.register()
    operators.register()


def unregister() -> None:
    """Unregister all addon classes and handlers."""
    operators.unregister()
    overlay.unregister()
    core.unregister()
    storage.unregister()
    preferences.unregister()
