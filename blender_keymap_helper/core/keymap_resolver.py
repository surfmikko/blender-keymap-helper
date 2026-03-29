"""Keymap resolution: combo strings, idname lookup, and display name derivation.

Provides functions to:
- Canonicalise a Blender event or keymap item into a stable combo string.
- Resolve a combo string to an ``(idname, display_name)`` pair by walking
  the active keyconfig with fallback to the default keyconfig.
- Derive a human-readable display name from a keymap item.
"""

import re
import sys

import bpy

from . import _log

# Modifier keys in canonical sort order.
# OSKEY = Cmd on macOS, Win key on Windows.
_MODIFIERS: tuple[str, ...] = ("ALT", "CTRL", "OSKEY", "SHIFT")

# Idname prefixes whose shortcuts are excluded from tracking.
# Order matters: pie-menu check must come before the generic call_menu check.
_EXCLUDED_IDNAME_PREFIXES: tuple[str, ...] = (
    "wm.call_panel",
    "wm.window_",
    "screen.",
)

# Generic kmi.name values that are not useful as display labels.
_GENERIC_KMI_NAMES: frozenset[str] = frozenset(
    {
        "Pie Menu on Drag",
        "Context Toggle",
        "Context Menu",
    }
)

# Property values that add no useful disambiguation (skip as suffix).
_UNINFORMATIVE_PROP_VALUES: frozenset[str] = frozenset(
    {"DEFAULT", "NONE", "STANDARD", ""}
)

# kmi.properties attributes checked in order for a disambiguation suffix.
_DISAMBIGUATING_PROPS: tuple[str, ...] = ("type", "mode", "action", "value")


def canonicalize_event(event: bpy.types.Event) -> str:
    """Return a canonical combo string for a Blender event.

    Modifiers are sorted alphabetically and joined with ``+``, followed
    by the event type.  Example outputs: ``"G"``, ``"CTRL+SHIFT+A"``,
    ``"ALT+RMB"``.

    Args:
        event: The Blender input event to canonicalise.

    Returns:
        A non-empty canonical combo string.
    """
    modifiers = [m for m in _MODIFIERS if getattr(event, m.lower(), False)]
    return "+".join(modifiers + [event.type])


def canonicalize_kmi(kmi: bpy.types.KeyMapItem) -> str:
    """Return a canonical combo string for a keymap item.

    Args:
        kmi: The keymap item to canonicalise.

    Returns:
        A non-empty canonical combo string.
    """
    modifiers = [m for m in _MODIFIERS if getattr(kmi, m.lower(), False)]
    return "+".join(modifiers + [kmi.type])


def is_excluded_idname(idname: str) -> bool:
    """Return ``True`` if the idname should never be tracked.

    Pie menu shortcuts (``wm.call_menu_pie*``) are explicitly included.
    Regular menu openers (``wm.call_menu`` non-pie) are excluded.

    Args:
        idname: The operator idname to test.

    Returns:
        ``True`` if the shortcut should be ignored, ``False`` otherwise.
    """
    if idname.startswith("wm.call_menu_pie"):
        return False
    if idname.startswith("wm.call_menu"):
        return True
    return any(idname.startswith(p) for p in _EXCLUDED_IDNAME_PREFIXES)


def resolve_combo(
    combo: str,
    area: bpy.types.Area | None,
) -> tuple[str, str] | None:
    """Resolve a combo string to ``(idname, display_name)`` for the given area.

    Walks ``keyconfigs.active`` first, then ``keyconfigs.default``.  Only
    keymaps whose ``space_type`` matches the area type (or ``"EMPTY"``
    for global shortcuts) are considered.

    Disabled kmi entries (``kmi.active == False``) are skipped — another
    active binding for the same combo may exist later in the same keyconfig
    (e.g. Blender's built-in binding after an addon binding is disabled).
    Only if *every* match in the active keyconfig is disabled, and there are
    no active matches at all, is ``None`` returned.

    Args:
        combo: Canonical combo string, e.g. ``"CTRL+A"``.
        area: The area under the mouse cursor, or ``None``.

    Returns:
        A ``(idname, display_name)`` tuple, or ``None`` if the combo is
        unbound or all matching bindings are disabled.
    """
    space_type: str = area.type if area else ""
    keyconfigs = bpy.context.window_manager.keyconfigs

    # Two-pass search: prefer bindings that fire on a plain PRESS; fall back to
    # CLICK_DRAG only if no press-compatible binding exists for this combo.
    for value_filter in ({"PRESS", "ANY", "CLICK"}, {"CLICK_DRAG"}):
        for kc in (keyconfigs.active, keyconfigs.default):
            for km in kc.keymaps:
                if km.space_type not in (space_type, "EMPTY"):
                    continue
                for kmi in km.keymap_items:
                    if canonicalize_kmi(kmi) != combo:
                        continue
                    if kmi.value not in value_filter:
                        continue
                    if not kmi.active:
                        _log(f"resolver: {combo} skipping disabled kmi ({kmi.idname!r})")
                        continue
                    display = _resolve_display_name(kmi)
                    _log(f"resolver: {combo} → {kmi.idname!r} ({display!r})")
                    return kmi.idname, display

    _log(f"resolver: {combo} → unbound")
    return None


def _pie_menu_label(kmi: bpy.types.KeyMapItem) -> str | None:
    """Return the ``bl_label`` of the pie menu this kmi opens, or ``None``.

    ``wm.call_menu_pie`` stores the menu class name in ``kmi.properties.name``.
    If the class is registered, its ``bl_label`` is a human-readable title.

    Args:
        kmi: A keymap item whose idname starts with ``"wm.call_menu_pie"``.

    Returns:
        The menu's ``bl_label``, or ``None`` if it cannot be resolved.
    """
    try:
        menu_class_name: str = kmi.properties.name
        if not menu_class_name:
            return None
        menu_cls = getattr(bpy.types, menu_class_name, None)
        if menu_cls is not None:
            label: str = getattr(menu_cls, "bl_label", "") or ""
            return label or None
    except (AttributeError, TypeError):
        pass
    return None


def _resolve_display_name(kmi: bpy.types.KeyMapItem) -> str:
    """Derive a human-readable display name from a keymap item.

    Resolution order:

    1. ``kmi.name`` if it is not a known generic label.
    2. The operator's ``bl_rna.name``.
    3. Prettified idname as a final fallback.

    In all cases, a disambiguation suffix is appended when ``kmi.properties``
    carries a discriminating attribute (e.g. ``type='VERT'``), so that
    bindings that share an operator name remain distinguishable.

    Args:
        kmi: The keymap item to derive a name for.

    Returns:
        A non-empty human-readable display name.
    """
    if kmi.name and kmi.name not in _GENERIC_KMI_NAMES:
        base = kmi.name
    elif kmi.idname.startswith("wm.call_menu_pie"):
        # Resolve to the pie menu's own bl_label rather than the operator name.
        base = _pie_menu_label(kmi) or _prettify_idname(kmi.idname)
    else:
        base = None
        try:
            op = getattr(bpy.ops, kmi.idname.replace(".", "_"), None)
            if op is not None:
                rna_name: str = op.bl_rna.name  # type: ignore[attr-defined]
                if rna_name:
                    base = rna_name
        except AttributeError:
            pass
        if base is None:
            base = _prettify_idname(kmi.idname)

    suffix = _kmi_property_suffix(kmi)
    return f"{base}: {suffix}" if suffix else base


def _kmi_property_suffix(kmi: bpy.types.KeyMapItem) -> str:
    """Return a disambiguation suffix from ``kmi.properties``, or ``""``.

    Checks a short list of common discriminating property names and returns
    the first enum-style value found that adds meaningful context.

    Args:
        kmi: The keymap item whose properties to inspect.

    Returns:
        A title-cased suffix string, or ``""`` if nothing useful was found.
    """
    try:
        props = kmi.properties
    except Exception:
        return ""
    for attr in _DISAMBIGUATING_PROPS:
        val = getattr(props, attr, None)
        if not isinstance(val, str):
            continue
        val = val.strip()
        if val in _UNINFORMATIVE_PROP_VALUES:
            continue
        # Only use short uppercase enum-style values (e.g. "VERT", "EDGE").
        if val == val.upper() and len(val) <= 24:
            return val.replace("_", " ").title()
    return ""


def resolve_idname(idname: str, space_type: str) -> str | None:
    """Return the canonical combo string bound to *idname* for *space_type*.

    Walks ``keyconfigs.active`` first, then ``keyconfigs.default``.  Only
    keymaps whose ``space_type`` matches *space_type* or ``"EMPTY"`` are
    considered.  Returns the combo for the first active binding found.

    Args:
        idname: Operator idname to look up, e.g. ``"transform.translate"``.
        space_type: Area type string, e.g. ``"VIEW_3D"``.

    Returns:
        Canonical combo string, or ``None`` if the idname is unbound.
    """
    keyconfigs = bpy.context.window_manager.keyconfigs
    for kc in (keyconfigs.active, keyconfigs.default):
        for km in kc.keymaps:
            if km.space_type not in (space_type, "EMPTY"):
                continue
            for kmi in km.keymap_items:
                if kmi.idname == idname and kmi.active:
                    return canonicalize_kmi(kmi)
    _log(f"resolver: idname {idname!r} → unbound in {space_type!r}")
    return None


def display_combo(combo: str) -> str:
    """Return a human-readable combo string for display in the overlay.

    Replaces internal modifier names with platform-friendly labels.
    On macOS: ``OSKEY`` → ``CMD``, ``ALT`` → ``OPTION``.

    Args:
        combo: Canonical combo string, e.g. ``"ALT+OSKEY+NUMPAD_1"``.

    Returns:
        Display combo string, e.g. ``"OPTION+CMD+NUMPAD_1"``.
    """
    result = combo.replace("OSKEY", "CMD")
    if sys.platform == "darwin":
        result = result.replace("ALT", "OPTION")
    return result


def _prettify_idname(idname: str) -> str:
    """Convert an operator idname to a readable label.

    Example: ``"object.select_all"`` → ``"Select All"``.

    Args:
        idname: Dot-separated operator idname.

    Returns:
        Title-cased label derived from the operator name portion.
    """
    name_part = idname.split(".")[-1]
    return re.sub(r"_+", " ", name_part).title()
