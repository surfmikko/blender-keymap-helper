"""Core logic: context keys, keymap resolution, scoring, and usage tracking."""

# Set to True to enable debug logging to the Blender console.
# Must remain False in production releases — zero console output when False.
DEBUG: bool = False


def _log(msg: str) -> None:
    """Print a debug message to the Blender console when :data:`DEBUG` is enabled.

    Args:
        msg: The message to print.
    """
    if DEBUG:
        print(f"[keymap_helper] {msg}")


def register() -> None:
    """Register core module and run startup cleanup."""
    import bpy
    from . import scorer

    _log("core: register")
    try:
        from .. import ADDON_PACKAGE
        prefs = bpy.context.preferences.addons[ADDON_PACKAGE].preferences
        scorer.cleanup_stale(prefs)
    except (KeyError, AttributeError):
        # Preferences not yet available during early registration — skip.
        pass


def unregister() -> None:
    """Unregister core module."""
    _log("core: unregister")
