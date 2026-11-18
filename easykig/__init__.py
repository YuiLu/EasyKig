"""EasyKig Blender add-on. This package does not vendor third-party source."""
bl_info = {
    "name": "EasyKig",
    "author": "EasyKig contributors",
    "version": (0, 1, 2),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > EasyKig",
    "description": "Edit individual component meshes with reference images and ShapeUp",
    "category": "3D View",
}

def register():
    from . import properties, connections, operators, mesh_operators, prompt_editor, panels

    properties.register()
    connections.register()
    operators.register()
    mesh_operators.register()
    prompt_editor.register()
    panels.register()


def unregister():
    from . import properties, connections, operators, mesh_operators, prompt_editor, panels

    panels.unregister()
    prompt_editor.unregister()
    mesh_operators.unregister()
    operators.unregister()
    connections.unregister()
    properties.unregister()
