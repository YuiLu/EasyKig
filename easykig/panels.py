from pathlib import Path
import bpy
from . import image_preview
from .prompt_editor import draw_prompt


class EASYKIG_PT_main(bpy.types.Panel):
    bl_label = 'EasyKig Component Editor'
    bl_idname = 'EASYKIG_PT_main'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'EasyKig'

    def draw(self, context):
        settings = context.scene.easykig_settings
        layout = self.layout
        source = layout.column(align=True)
        source.enabled = not settings.mesh_job_running
        source.use_property_split = True
        source.use_property_decorate = False
        source.prop(settings, 'face')
        source.operator('easykig.pick_face')
        reference = source.box()
        row = reference.row(align=True)
        row.label(text='Component Reference', icon='IMAGE_DATA')
        if settings.mesh_edit_image:
            row.operator('easykig.set_reference', text='', icon='X').clear = True
        reference.operator('easykig.set_reference', text='Drop Image or Browse', icon='FILE_IMAGE')
        if image_preview.preview_icon(settings.mesh_edit_image):
            popup = max(9, min(22, (context.window.height - 60) / (40 * context.preferences.system.ui_scale)))
            reference.template_icon_view(settings, 'reference_thumbnail', scale=7, scale_popup=popup)
            reference.label(text=Path(settings.mesh_edit_image).name, translate=False)
        draw_prompt(source, context, settings)
        source.label(text='ShapeUp uses the reference image.')
        header, options = source.panel('EASYKIG_sampling', default_closed=True)
        header.label(text='Sampling Options')
        if options:
            options.prop(settings, 'mesh_edit_seed')
            options.prop(settings, 'mesh_edit_steps')
            options.prop(settings, 'mesh_edit_resolution')
        start = layout.row(align=True)
        start.enabled = bool(settings.face and settings.mesh_edit_image and not settings.mesh_job_running and context.mode == 'OBJECT')
        start.operator('easykig.remote_mesh_edit', text='Edit Component', icon='MESH_DATA')
        if settings.mesh_job_running:
            layout.operator('easykig.stop_mesh_wait', icon='PAUSE')
        else:
            layout.operator('easykig.resume_mesh_job')
        layout.label(text='Status ' + settings.mesh_job_status)
        if settings.mesh_job_id:
            layout.prop(settings, 'mesh_job_id', text='Task ID')
        if settings.mesh_job_message:
            layout.label(text=settings.mesh_job_message[:110])
        if settings.mesh_result_glb:
            layout.operator('easykig.import_mesh_result', icon='IMPORT')


def register():
    image_preview.register()
    bpy.utils.register_class(EASYKIG_PT_main)


def unregister():
    bpy.utils.unregister_class(EASYKIG_PT_main)
    image_preview.unregister()
