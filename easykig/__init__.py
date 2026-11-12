"""EasyKig Blender add-on. This package does not vendor third-party source."""
bl_info = {
    "name": "EasyKig",
    "author": "EasyKig contributors",
    "version": (0, 1, 1),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > EasyKig",
    "description": "PMX preprocessing, template morph editing, white-shell preview and remote AI finishing",
    "category": "3D View",
}

def register():
    from . import properties, operators, panels

    properties.register()
    operators.register()
    panels.register()


def unregister():
    from . import properties, operators, panels

    panels.unregister()
    operators.unregister()
    properties.unregister()
