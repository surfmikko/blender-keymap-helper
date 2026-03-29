"""Viewport overlay rendering."""

from . import draw  # noqa: F401


def register() -> None:
    """Register overlay module."""
    draw.register()


def unregister() -> None:
    """Unregister overlay module."""
    draw.unregister()
