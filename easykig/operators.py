"""Component reference input and mesh selection."""
from pathlib import Path
import tempfile
import bpy
from bpy.props import BoolProperty, StringProperty
from .remote import REFERENCE_EXTENSIONS, validate_reference_image


def _prefs(context):
    return context.preferences.addons[__package__].preferences


def _face(context):
    obj = context.scene.easykig_settings.face
    if obj is None or obj.type != 'MESH':
        raise ValueError('Choose a component source mesh')
    return obj


def _notify_failure(operator, error):
    operator.report({'ERROR'}, str(error)[:350])
    return {'CANCELLED'}


def output_folder(settings):
    path = _prefs(bpy.context).preview_directory or settings.preview_output_dir
    if not path or (path.startswith('//') and not bpy.data.filepath):
        folder = Path(tempfile.gettempdir()) / 'easykig_outputs'
    else:
        folder = Path(bpy.path.abspath(path))
    folder.mkdir(parents=True, exist_ok=True)
    return folder


class EASYKIG_OT_pick_face(bpy.types.Operator):
    bl_idname = 'easykig.pick_face'
    bl_label = 'Use Selected Mesh'

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            return _notify_failure(self, ValueError('Select one component mesh'))
        context.scene.easykig_settings.face = obj
        return {'FINISHED'}


class EASYKIG_OT_set_reference(bpy.types.Operator):
    bl_idname = 'easykig.set_reference'
    bl_label = 'Choose Component Reference'
    filepath: StringProperty(subtype='FILE_PATH', options={'SKIP_SAVE'})
    filter_glob: StringProperty(default=';'.join('*' + suffix for suffix in REFERENCE_EXTENSIONS), options={'HIDDEN'})
    clear: BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context, _event):
        if self.filepath or self.clear:
            return self.execute(context)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        try:
            path = '' if self.clear else str(validate_reference_image(bpy.path.abspath(self.filepath)).resolve())
            context.scene.easykig_settings.mesh_edit_image = path
            return {'FINISHED'}
        except (OSError, ValueError) as error:
            return _notify_failure(self, error)


class EASYKIG_FH_reference(bpy.types.FileHandler):
    bl_idname = 'EASYKIG_FH_reference'
    bl_label = 'EasyKig Component Reference'
    bl_import_operator = 'easykig.set_reference'
    bl_file_extensions = ';'.join(REFERENCE_EXTENSIONS)

    @classmethod
    def poll_drop(cls, context):
        return bool(context.area and context.area.type == 'VIEW_3D' and any(
            region.type == 'UI' and region.active_panel_category == 'EasyKig' for region in context.area.regions))


class EASYKIG_OT_paste_editing_prompt(bpy.types.Operator):
    bl_idname = 'easykig.paste_editing_prompt'
    bl_label = 'Paste Editing Notes'
    clear: BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        value = '' if self.clear else context.window_manager.clipboard
        if len(value) > 1500:
            return _notify_failure(self, ValueError('Editing notes exceed 1,500 characters'))
        context.scene.easykig_settings.editing_prompt = value
        return {'FINISHED'}


_CLASSES = (EASYKIG_OT_pick_face, EASYKIG_OT_set_reference, EASYKIG_FH_reference, EASYKIG_OT_paste_editing_prompt)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
