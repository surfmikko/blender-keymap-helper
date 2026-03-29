"""draw_handler callback and BLF/GPU rendering.

Renders a two-column overlay in the corner of the 3D viewport.
The callback polls the current context key on each draw and refreshes the
displayed entries when the context changes.
"""

import blf
import gpu
from gpu_extras.batch import batch_for_shader

import bpy

from ..core import _log
from ..core.context import compute_context_key
from ..core import keymap_resolver, scorer
from ..core.keymap_resolver import display_combo
from ..storage import store

# Handle returned by draw_handler_add; stored for unregistration.
_draw_handle: object = None

# Cache to avoid re-scoring on every draw when nothing has changed.
# Invalidated when context key changes OR store generation changes.
_cached_context_key: str = ""
_cached_generation: int = -1
_cached_entries: list[tuple[str, str]] = []

# HUD clearance in viewport-local pixels.
# Sampled inline on every draw for immediate response; the timer is a fallback
# that triggers a redraw when HUD state changes without user interaction.
_hud_clearance: int = 0

_HUD_TIMER_INTERVAL: float = 1.0

# Layout constants.
_FONT_ID: int = 0
_BASE_FONT_SIZE: int = 12
_LINE_PADDING: int = 4
_COLUMN_GAP: int = 16
_BOX_PADDING_X: int = 10
_BOX_PADDING_Y: int = 8

# Fallback colours used when theme access fails.
_FALLBACK_COLORS: dict[str, tuple[float, float, float, float]] = {
    "box":   (0.0, 0.0, 0.0, 0.40),
    "combo": (0.8, 0.7, 0.3, 0.90),
    "name":  (0.7, 0.7, 0.7, 0.90),
}


def _theme_colors(prefs: object) -> dict[str, tuple[float, float, float, float]]:
    """Derive overlay colours from the active Blender theme.

    Uses three theme properties:

    * ``view_3d.space.back`` — viewport background, shifted slightly toward
      mid-grey so the overlay box is visually distinct from the scene.
    * ``user_interface.wcol_regular.text`` — standard panel text; used for
      action names so they match the rest of the Blender UI.
    * ``view_3d.space.header_text_hi`` — highlighted header text, which is
      the theme's accent colour; used for key combo labels.

    The ``contrast`` preference scales the alpha values: LOW uses reduced
    opacity for a subtle look; HIGH uses full opacity.

    Args:
        prefs: Addon preferences with a ``contrast`` attribute.

    Returns:
        Dict with ``"box"``, ``"combo"``, and ``"name"`` RGBA tuples.
    """
    try:
        theme = bpy.context.preferences.themes[0]
        ui = theme.user_interface
        v3d = theme.view_3d

        contrast: str = getattr(prefs, "contrast", "LOW")
        box_alpha: float = 0.38 if contrast == "LOW" else 0.58
        text_alpha: float = 0.80 if contrast == "LOW" else 1.0

        # Background: viewport colour shifted toward mid-grey for definition.
        bg = v3d.space.back
        brightness = (bg[0] + bg[1] + bg[2]) / 3.0
        shift = 0.12 if brightness < 0.5 else -0.12
        box_rgb = (
            max(0.0, min(1.0, bg[0] + shift)),
            max(0.0, min(1.0, bg[1] + shift)),
            max(0.0, min(1.0, bg[2] + shift)),
        )

        # Name text: standard UI panel text colour.
        tc = ui.wcol_regular.text
        name_rgb = (tc[0], tc[1], tc[2])

        # Combo accent: header highlighted text (theme primary accent).
        ac = v3d.space.header_text_hi
        combo_rgb = (ac[0], ac[1], ac[2])

        return {
            "box":   (*box_rgb,   box_alpha),
            "combo": (*combo_rgb, text_alpha),
            "name":  (*name_rgb,  text_alpha),
        }
    except Exception:
        return dict(_FALLBACK_COLORS)


def _get_prefs() -> object | None:
    """Return addon preferences, or ``None`` if not available.

    Returns:
        The ``CheatsheetPreferences`` instance or ``None``.
    """
    from .. import ADDON_PACKAGE
    try:
        return bpy.context.preferences.addons[ADDON_PACKAGE].preferences
    except (KeyError, AttributeError):
        return None


def _font_size(prefs: object) -> int:
    """Compute the effective font size from preferences and UI scale.

    Args:
        prefs: Addon preferences with ``font_size_offset`` attribute.

    Returns:
        Font size in points, scaled by the Blender UI scale factor.
    """
    ui_scale: float = bpy.context.preferences.system.ui_scale
    offset: int = getattr(prefs, "font_size_offset", 0)
    return max(6, round((_BASE_FONT_SIZE + offset) * ui_scale))


def _draw_rect(
    x: float, y: float, w: float, h: float,
    color: tuple[float, float, float, float],
) -> None:
    """Draw a filled rectangle using the GPU uniform colour shader.

    Args:
        x: Left edge in region pixels.
        y: Bottom edge in region pixels.
        w: Width in pixels.
        h: Height in pixels.
        color: RGBA colour tuple.
    """
    vertices = (
        (x, y), (x + w, y),
        (x, y + h), (x + w, y + h),
    )
    indices = ((0, 1, 2), (1, 3, 2))
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    batch = batch_for_shader(shader, "TRIS", {"pos": vertices}, indices=indices)
    gpu.state.blend_set("ALPHA")
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    gpu.state.blend_set("NONE")


def _read_hud_clearance(area: object, window_region: object) -> int:
    """Sample the HUD region height for *area* and return viewport-local clearance.

    Args:
        area: A ``bpy.types.Area`` of type ``VIEW_3D``.
        window_region: The WINDOW ``bpy.types.Region`` for that area.

    Returns:
        Pixels from the bottom of the viewport to the top of the HUD, or 0.
    """
    for r in getattr(area, "regions", ()):
        if r.type != "HUD" or r.height <= 30 or r.width <= 1:
            continue
        candidate: int = (r.y + r.height) - window_region.y
        if 0 < candidate < window_region.height:
            return candidate
    return 0


def _hud_timer() -> float:
    """Fallback timer: trigger a redraw when HUD state changes without interaction.

    The draw callback samples the HUD on every redraw for immediate response.
    This timer handles the edge case where the HUD appears or disappears with
    no user interaction to trigger a redraw (e.g. an automated operator).

    Returns:
        Seconds until the next call.
    """
    global _hud_clearance

    new_clearance: int = 0
    try:
        screen = bpy.context.screen
        if screen:
            for area in screen.areas:
                if area.type != "VIEW_3D":
                    continue
                win = next((r for r in area.regions if r.type == "WINDOW"), None)
                if win is not None:
                    new_clearance = _read_hud_clearance(area, win)
                break
    except Exception:
        pass

    if new_clearance != _hud_clearance:
        _log(f"draw: HUD clearance (timer) → {new_clearance}px")
        try:
            for area in bpy.context.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
        except Exception:
            pass

    return _HUD_TIMER_INTERVAL


def _draw_callback() -> None:
    """Viewport draw callback — renders the overlay.

    Called by Blender on every viewport redraw via ``POST_PIXEL``.
    Accesses the live context through ``bpy.context``.
    """
    global _cached_context_key, _cached_generation, _cached_entries, _hud_clearance

    context = bpy.context
    prefs = _get_prefs()
    if prefs is None:
        return
    if not getattr(prefs, "enabled", True):
        return

    # Only draw in VIEW_3D.
    area = getattr(context, "area", None)
    if area is None or area.type != "VIEW_3D":
        return
    region = getattr(context, "region", None)
    if region is None or region.type != "WINDOW":
        return

    # Sample HUD clearance on every draw for immediate position response.
    new_hud = _read_hud_clearance(area, region)
    if new_hud != _hud_clearance:
        _hud_clearance = new_hud
        _log(f"draw: HUD clearance → {_hud_clearance}px")

    # Refresh entries when context or store data changes.
    context_key = compute_context_key(context)
    if context_key != _cached_context_key or store.generation != _cached_generation:
        _cached_context_key = context_key
        _cached_generation = store.generation
        _cached_entries = scorer.get_display_entries(
            context_key, prefs, keymap_resolver
        )
        _log(f"draw: cache refreshed → {context_key!r} gen={_cached_generation} ({len(_cached_entries)} entries)")

    entries = _cached_entries
    if not entries:
        return

    fsize = _font_size(prefs)
    blf.size(_FONT_ID, fsize)
    line_height = fsize + _LINE_PADDING

    # Measure column widths using display strings.
    combo_width = max(blf.dimensions(_FONT_ID, display_combo(combo))[0] for combo, _ in entries)
    name_width = max(blf.dimensions(_FONT_ID, name)[0] for _, name in entries)

    box_w = _BOX_PADDING_X * 2 + combo_width + _COLUMN_GAP + name_width
    box_h = _BOX_PADDING_Y * 2 + line_height * len(entries)

    margin_x: int = getattr(prefs, "margin_x", 20)
    margin_y: int = getattr(prefs, "margin_y", 20)
    position: str = getattr(prefs, "position", "BOTTOM_LEFT")

    if position == "BOTTOM_RIGHT":
        box_x = region.width - box_w - margin_x
    else:
        box_x = margin_x

    box_y = max(margin_y, _hud_clearance + margin_y)

    palette = _theme_colors(prefs)
    _draw_rect(box_x, box_y, box_w, box_h, palette["box"])

    for i, (combo, name) in enumerate(entries):
        line_y = box_y + _BOX_PADDING_Y + i * line_height

        # Key combo — right-aligned within the combo column.
        label = display_combo(combo)
        cw = blf.dimensions(_FONT_ID, label)[0]
        blf.position(_FONT_ID, box_x + _BOX_PADDING_X + combo_width - cw, line_y, 0)
        blf.color(_FONT_ID, *palette["combo"])
        blf.draw(_FONT_ID, label)

        # Action name — left-aligned after the gap.
        blf.position(
            _FONT_ID,
            box_x + _BOX_PADDING_X + combo_width + _COLUMN_GAP,
            line_y, 0,
        )
        blf.color(_FONT_ID, *palette["name"])
        blf.draw(_FONT_ID, name)


def register() -> None:
    """Register the viewport draw handler and HUD poll timer."""
    global _draw_handle
    _draw_handle = bpy.types.SpaceView3D.draw_handler_add(
        _draw_callback, (), "WINDOW", "POST_PIXEL"
    )
    bpy.app.timers.register(_hud_timer, first_interval=_HUD_TIMER_INTERVAL, persistent=True)
    _log("draw: handler registered")


def unregister() -> None:
    """Unregister the viewport draw handler and HUD poll timer."""
    global _draw_handle, _cached_context_key, _cached_entries, _hud_clearance
    if bpy.app.timers.is_registered(_hud_timer):
        bpy.app.timers.unregister(_hud_timer)
    if _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, "WINDOW")
        _draw_handle = None
    _cached_context_key = ""
    _cached_entries = []
    _hud_clearance = 0
    _log("draw: handler unregistered")
