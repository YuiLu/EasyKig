"""Evaluated copies for nondestructive component export."""
import bpy


def rank_face_objects(objects):
    return sorted((obj for obj in objects if obj.type == 'MESH'), key=lambda obj: len(obj.data.vertices), reverse=True)


def evaluated_copy(context, obj, name="Kig Working Face"):
    """Bake active morph / armature into a new static working mesh; preserves source object."""
    depsgraph = context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=depsgraph)
    copy_obj = bpy.data.objects.new(name, mesh)
    context.collection.objects.link(copy_obj)
    copy_obj.matrix_world = obj.matrix_world.copy()
    copy_obj["easykig_role"] = "working_face"
    return copy_obj
