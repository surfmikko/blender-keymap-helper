"""Toggle overlay and clear memory operators."""

import json
import time
from pathlib import Path

import bpy

from ..core import _log


def _get_prefs(context: bpy.types.Context) -> object | None:
    from .. import ADDON_PACKAGE
    try:
        return context.preferences.addons[ADDON_PACKAGE].preferences
    except (KeyError, AttributeError):
        return None


class CheatsheetToggleOperator(bpy.types.Operator):
    """Toggle the overlay overlay on or off."""

    bl_idname = "keymap_helper.toggle"
    bl_label = "Toggle Cheatsheet"
    bl_description = "Show or hide the shortcut overlay overlay"

    def execute(self, context: bpy.types.Context) -> set:
        """Flip the enabled preference and redraw all 3D viewports.

        Args:
            context: The active Blender context.

        Returns:
            ``{'FINISHED'}``
        """
        prefs = _get_prefs(context)
        if prefs is None:
            return {"CANCELLED"}
        prefs.enabled = not prefs.enabled
        _log(f"commands: overlay {'shown' if prefs.enabled else 'hidden'}")
        for area in context.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()
        return {"FINISHED"}


class CheatsheetClearMemoryOperator(bpy.types.Operator):
    """Clear all stored shortcut usage statistics."""

    bl_idname = "keymap_helper.clear_memory"
    bl_label = "Clear Cheatsheet Memory"
    bl_description = "Delete all recorded shortcut usage data"

    def execute(self, context: bpy.types.Context) -> set:
        """Wipe the store and redraw all 3D viewports.

        Args:
            context: The active Blender context.

        Returns:
            ``{'FINISHED'}``
        """
        from ..storage import store
        store.clear_all()
        _log("commands: memory cleared")
        for area in context.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()
        return {"FINISHED"}


class CheatsheetResetOperator(bpy.types.Operator):
    """Populate the data store with curated default shortcuts."""

    bl_idname = "keymap_helper.reset_to_defaults"
    bl_label = "Reset to Defaults"
    bl_description = (
        "Add the default shortcut set to the overlay based on the active keymap"
    )

    def execute(self, context: bpy.types.Context) -> set:
        """Load defaults.json and seed the store with default shortcuts.

        Steps:
        1. Detect active keymap variant from ``keyconfigs.active.name``.
        2. Load matching context sections from ``defaults.json``.
        3. For each idname, resolve the current key combo from the active
           keymap (falling back to the default keymap).
        4. Add to the store at ``count=0`` if not already present.
        5. Save the store.

        Args:
            context: The active Blender context.

        Returns:
            ``{'FINISHED'}``
        """
        from ..core.keymap_resolver import resolve_idname
        from ..storage import store

        defaults_path = Path(__file__).parent.parent / "data" / "defaults.json"
        try:
            defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _log(f"reset: failed to load defaults.json: {exc}")
            self.report({"ERROR"}, f"Could not load defaults: {exc}")
            return {"CANCELLED"}

        # Normalise the active keyconfig name to a variants key.
        active_name: str = (
            context.window_manager.keyconfigs.active.name.lower().replace(" ", "_")
        )
        variants: dict = defaults.get("variants", {})
        variant_key = active_name if active_name in variants else "blender"
        variant_data: dict = variants.get(variant_key, {})
        _log(f"reset: using variant {variant_key!r}")

        now: float = time.time()
        added: int = 0

        for context_key, idnames in variant_data.items():
            # Derive space_type from the first segment of the context key.
            space_type: str = context_key.split("#")[0]
            for idname in idnames:
                combo = resolve_idname(idname, space_type)
                if combo is None:
                    _log(f"reset: {idname!r} unbound, skipping")
                    continue
                if store.get_entry(context_key, combo) is not None:
                    _log(f"reset: {context_key} {combo} already tracked, skipping")
                    continue
                store.upsert_entry(
                    context_key,
                    combo,
                    {"count": 0, "last_used": 0.0, "first_used": now},
                )
                _log(f"reset: added {context_key} {combo} ({idname!r})")
                added += 1

        store.save()
        _log(f"reset: done — {added} entries added")
        self.report({"INFO"}, f"Reset to defaults: {added} shortcuts added.")

        for area in context.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()
        return {"FINISHED"}
