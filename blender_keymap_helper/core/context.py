"""Context key computation from the live Blender context."""


def compute_context_key(context: object) -> str:
    """Derive a stable, unique string key from the current Blender editor context.

    The key is a ``#``-separated string of the relevant context variables.
    Missing or inapplicable values are omitted. Example outputs::

        VIEW_3D#OBJECT#WINDOW
        VIEW_3D#EDIT_MESH#WINDOW
        NODE_EDITOR#OBJECT#WINDOW

    Args:
        context: The active Blender context (``bpy.context``).

    Returns:
        A non-empty string uniquely identifying the current editor context.
    """
    parts = [
        getattr(getattr(context, "area", None), "type", ""),
        getattr(context, "mode", ""),
        getattr(getattr(context, "region", None), "type", ""),
    ]
    return "#".join(p for p in parts if p)
