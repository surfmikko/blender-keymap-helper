"""Persistent modal operator for capturing keypresses and mouse clicks."""

import bpy

from ..core import _log
from ..core.keymap_resolver import canonicalize_event, is_excluded_idname, resolve_combo
from ..core.tracker import record_event

# Event types that are never tracked.
_EXCLUDED_TYPES: frozenset[str] = frozenset(
    {
        "MOUSEMOVE",
        "INBETWEEN_MOUSEMOVE",
        "WHEELLEFTMOUSE",
        "WHEELRIGHTMOUSE",
        "WHEELINMOUSE",
        "WHEELOUTMOUSE",
        "TIMER",
        "TIMER0",
        "TIMER1",
        "TIMER2",
        "TIMER_JOBS",
        "NONE",
        "WINDOW_DEACTIVATE",
    }
)

# Mouse button types — used for drag gesture detection.
_MOUSE_BUTTONS: frozenset[str] = frozenset(
    {"LEFTMOUSE", "RIGHTMOUSE", "MIDDLEMOUSE"}
)

# Modifier key types — used for drag gesture detection.
_MODIFIER_KEYS: frozenset[str] = frozenset(
    {"LEFT_SHIFT", "RIGHT_SHIFT", "LEFT_CTRL", "RIGHT_CTRL", "LEFT_ALT", "RIGHT_ALT"}
)

# Supported area types in v1.
_SUPPORTED_SPACES: frozenset[str] = frozenset({"VIEW_3D"})

# Set of active tracker instance ids. Populated on invoke, cleared on cancel.
# Used by the watchdog to detect if the tracker has died.
_active_trackers: set[int] = set()


def _area_at_mouse(mx: int, my: int) -> bpy.types.Area | None:
    """Return the screen area under the given mouse coordinates, or ``None``.

    Blender routes key events to the area under the mouse cursor, so this
    matches how Blender itself determines which shortcuts are active.

    Args:
        mx: Mouse X coordinate in screen pixels.
        my: Mouse Y coordinate in screen pixels.

    Returns:
        The ``bpy.types.Area`` under the cursor, or ``None``.
    """
    try:
        for area in bpy.context.screen.areas:
            if area.x <= mx <= area.x + area.width:
                if area.y <= my <= area.y + area.height:
                    return area
    except AttributeError:
        pass
    return None


def _context_key_from_area(area: bpy.types.Area | None) -> str:
    """Derive a context key string from an area and the current Blender mode.

    Args:
        area: The area under the mouse cursor, or ``None``.

    Returns:
        A ``#``-separated context key string.
    """
    area_type: str = area.type if area else ""
    mode: str = getattr(bpy.context, "mode", "")
    parts = [p for p in (area_type, mode, "WINDOW") if p]
    return "#".join(parts)


class CheatsheetTrackerOperator(bpy.types.Operator):
    """Persistent background operator that captures shortcut usage statistics."""

    bl_idname = "keymap_helper.start_tracker"
    bl_label = "Cheatsheet Tracker"
    bl_options = {"INTERNAL"}

    # Drag gesture state: combo string while a button/modifier is held,
    # or None when no gesture is in progress.
    _drag_combo: str | None = None
    _drag_moved: bool = False

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set:
        """Start the modal loop.

        Args:
            context: The active Blender context.
            event: The invoking event.

        Returns:
            ``{'RUNNING_MODAL'}`` to enter the modal loop.
        """
        context.window_manager.modal_handler_add(self)
        _active_trackers.add(id(self))
        _log("tracker: started")
        return {"RUNNING_MODAL"}

    def modal(self, context: bpy.types.Context, event: bpy.types.Event) -> set:
        """Process each event. Never consumes events.

        Args:
            context: The active Blender context.
            event: The current event.

        Returns:
            ``{'PASS_THROUGH'}`` always.
        """
        area = _area_at_mouse(event.mouse_x, event.mouse_y)

        # --- Drag gesture handling ---
        if event.type == "MOUSEMOVE" and self._drag_combo is not None:
            self._drag_moved = True
            return {"PASS_THROUGH"}

        if event.value == "RELEASE" and self._drag_combo is not None:
            if self._drag_moved and area is not None and area.type in _SUPPORTED_SPACES:
                context_key = _context_key_from_area(area)
                resolved = resolve_combo(self._drag_combo, area)
                if resolved is not None:
                    idname, _ = resolved
                    record_event(context_key, self._drag_combo)
                    _log(f"tracker: drag [{context_key}] {self._drag_combo} → {idname!r}")
            self._drag_combo = None
            self._drag_moved = False
            return {"PASS_THROUGH"}

        # --- Normal press handling ---
        if not self._should_track(area, event):
            return {"PASS_THROUGH"}

        combo = canonicalize_event(event)

        # Start a drag gesture for mouse buttons and modifier keys.
        if event.type in _MOUSE_BUTTONS or event.type in _MODIFIER_KEYS:
            self._drag_combo = combo
            self._drag_moved = False
            # Also record as a plain click — drag check on release may add a second
            # count only if the mouse actually moved.
            resolved = resolve_combo(combo, area)
            if resolved is not None:
                idname, display_name = resolved
                if not is_excluded_idname(idname):
                    context_key = _context_key_from_area(area)
                    record_event(context_key, combo)
                    _log(
                        f"tracker: [{context_key}] {combo}"
                        f" → {idname!r} ({display_name!r})"
                    )
                else:
                    _log(f"tracker: skipping excluded idname {idname!r}")
            return {"PASS_THROUGH"}

        # Plain keypress.
        resolved = resolve_combo(combo, area)
        if resolved is not None:
            idname, display_name = resolved
            if not is_excluded_idname(idname):
                context_key = _context_key_from_area(area)
                record_event(context_key, combo)
                _log(
                    f"tracker: [{context_key}] {combo}"
                    f" → {idname!r} ({display_name!r})"
                )
            else:
                _log(f"tracker: skipping excluded idname {idname!r}")

        return {"PASS_THROUGH"}

    def cancel(self, context: bpy.types.Context) -> None:
        """Called when the operator is cancelled.

        Args:
            context: The active Blender context.
        """
        _active_trackers.discard(id(self))
        _log("tracker: cancelled")

    @staticmethod
    def _should_track(
        area: bpy.types.Area | None, event: bpy.types.Event
    ) -> bool:
        """Return ``True`` if this event should be tracked.

        Args:
            area: The area under the mouse cursor, or ``None``.
            event: The event to evaluate.

        Returns:
            ``True`` if the event passes all filters.
        """
        if event.value != "PRESS":
            return False
        if event.type in _EXCLUDED_TYPES:
            return False
        if area is None:
            return False
        if area.type not in _SUPPORTED_SPACES:
            return False
        return True


def watchdog() -> float:
    """Timer callback that restarts the tracker if it has stopped running.

    Returns:
        Seconds until the next check.
    """
    if not _active_trackers:
        _log("watchdog: tracker not running, restarting")
        try:
            bpy.ops.keymap_helper.start_tracker("INVOKE_DEFAULT")
        except Exception as exc:
            _log(f"watchdog: restart failed: {exc}")
    return 5.0
