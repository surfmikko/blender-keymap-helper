"""Startup script for development preview.

Adds the addon's parent directory to sys.path and enables the addon.
Passed to Blender via --python on launch.
"""

import sys
from pathlib import Path

import bpy

# Parent of the addon package must be on sys.path for the import to resolve.
addon_parent = str(Path(__file__).resolve().parents[2])
if addon_parent not in sys.path:
    sys.path.insert(0, addon_parent)

bpy.ops.preferences.addon_enable(module="blender_keymap_helper")
