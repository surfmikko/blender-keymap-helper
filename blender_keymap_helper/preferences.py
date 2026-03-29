"""Addon preferences."""

import bpy


class CheatsheetPreferences(bpy.types.AddonPreferences):
    """Configuration for the Cheatsheet addon."""

    bl_idname = __package__

    # --- Visibility ---

    enabled: bpy.props.BoolProperty(
        name="Show Cheatsheet",
        description="Display the shortcut overlay in the viewport",
        default=True,
    )  # type: ignore[assignment]

    # --- Layout ---

    position: bpy.props.EnumProperty(
        name="Position",
        description="Corner of the 3D viewport where the overlay appears",
        items=[
            ("BOTTOM_LEFT", "Bottom Left", ""),
            ("BOTTOM_RIGHT", "Bottom Right", ""),
        ],
        default="BOTTOM_LEFT",
    )  # type: ignore[assignment]

    margin_left: bpy.props.IntProperty(
        name="Left Margin",
        description="Distance from the left viewport edge in pixels",
        default=124,
        min=0,
        max=500,
        subtype="PIXEL",
    )  # type: ignore[assignment]

    margin_right: bpy.props.IntProperty(
        name="Right Margin",
        description="Distance from the right viewport edge in pixels",
        default=20,
        min=0,
        max=500,
        subtype="PIXEL",
    )  # type: ignore[assignment]

    margin_y: bpy.props.IntProperty(
        name="Vertical Margin",
        description="Distance from the viewport bottom edge (or HUD) in pixels",
        default=20,
        min=0,
        max=2000,
        subtype="PIXEL",
    )  # type: ignore[assignment]

    font_size_offset: bpy.props.IntProperty(
        name="Font Size Offset",
        description="Adjust the overlay font size relative to the base size (12 pt)",
        default=-2,
        min=-6,
        max=24,
    )  # type: ignore[assignment]

    contrast: bpy.props.EnumProperty(
        name="Contrast",
        description="Colour intensity of the overlay text and background",
        items=[
            ("LOW", "Low Contrast", "Muted colours that blend into the viewport"),
            ("HIGH", "High Contrast", "Vivid colours for maximum readability"),
        ],
        default="LOW",
    )  # type: ignore[assignment]

    # --- Scoring ---

    max_entries: bpy.props.IntProperty(
        name="Max Entries",
        description="Maximum number of shortcuts shown in the overlay at once",
        default=10,
        min=1,
        max=30,
    )  # type: ignore[assignment]

    mastery_count: bpy.props.IntProperty(
        name="Mastery Count",
        description="Number of uses after which a shortcut is considered mastered",
        default=20,
        min=5,
        max=200,
    )  # type: ignore[assignment]

    mastery_age_days: bpy.props.IntProperty(
        name="Mastery Age (days)",
        description="Days of use required alongside mastery count to suppress a shortcut",
        default=14,
        min=1,
        max=365,
    )  # type: ignore[assignment]

    # --- Cleanup ---

    cleanup_abandoned_days: bpy.props.IntProperty(
        name="Forget After (days)",
        description="Remove shortcuts not used for this many days",
        default=365,
        min=30,
        max=3650,
    )  # type: ignore[assignment]

    def draw(self, context: bpy.types.Context) -> None:
        """Draw the preferences panel.

        Args:
            context: The active Blender context.
        """
        layout = self.layout

        # Visibility + shortcuts hint
        row = layout.row()
        row.prop(self, "enabled", text="Enable Overlay")

        layout.separator()

        # Layout
        box = layout.box()
        box.label(text="Layout", icon="FULLSCREEN_ENTER")
        row = box.row()
        row.prop(self, "position", expand=True)
        row = box.row(align=True)
        row.prop(self, "margin_left")
        row.prop(self, "margin_right")
        row.prop(self, "margin_y")
        box.prop(self, "font_size_offset")
        box.prop(self, "contrast", expand=True)

        layout.separator()

        # Scoring
        box = layout.box()
        box.label(text="Scoring", icon="SORTTIME")
        box.prop(self, "max_entries")
        row = box.row(align=True)
        row.prop(self, "mastery_count")
        row.prop(self, "mastery_age_days")

        layout.separator()

        # Defaults / Cleanup
        box = layout.box()
        box.label(text="Defaults & Cleanup", icon="TRASH")
        box.operator("keymap_helper.reset_to_defaults", icon="FILE_REFRESH")
        box.prop(self, "cleanup_abandoned_days")
        box.operator("keymap_helper.clear_memory", icon="X")

        layout.separator()

        # Shortcuts reference
        box = layout.box()
        box.label(text="Shortcuts", icon="KEYINGSET")
        col = box.column(align=True)
        col.label(text="Ctrl+Shift+H — Toggle overlay")
        col.label(text="Ctrl+Shift+Del — Clear memory")


def register() -> None:
    """Register preferences class."""
    bpy.utils.register_class(CheatsheetPreferences)


def unregister() -> None:
    """Unregister preferences class."""
    bpy.utils.unregister_class(CheatsheetPreferences)
