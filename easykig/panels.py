from pathlib import Path

import bpy

from . import image_preview
from .components import component_state, component_template
from .properties import MAX_REFERENCE_IMAGES
from .mesh_operators import target_image
from .prompt_editor import draw_prompt


def _thumbnail_row(layout, context, owner, property_name, filename, scale=7.0):
    if not image_preview.preview_icon(filename):
        return False
    row = layout.row()
    row.alignment = 'CENTER'
    ui_scale = context.preferences.system.ui_scale
    popup_scale = max(9.0, min(22.0, (context.window.height - 60) / (40 * ui_scale)))
    row.template_icon_view(owner, property_name, scale=scale, scale_popup=popup_scale)
    return True


def _draw_references(layout, settings, context):
    entries = []
    if settings.reference_image:
        entries.append((settings, 'reference_thumbnail', settings.reference_image))
    entries.extend((item, 'thumbnail', item.path) for item in settings.extra_references)

    reference = layout.box()
    header = reference.row()
    header.label(text='References', icon='IMAGE_DATA')
    count = header.row()
    count.alignment = 'RIGHT'
    count.label(text=f'{len(entries)} / {MAX_REFERENCE_IMAGES}')
    add = reference.row()
    add.enabled = len(entries) < MAX_REFERENCE_IMAGES
    add.scale_y = 1.25
    add.operator('easykig.set_reference', text='Add Images' if entries else 'Drop Images or Browse', icon='ADD')
    if not entries:
        return

    width = context.region.width / context.preferences.system.ui_scale
    columns = 2 if len(entries) > 1 and width >= 220 else 1
    cards = reference.grid_flow(columns=columns, row_major=True, even_columns=True, even_rows=True)
    for index, (owner, prop, filename) in enumerate(entries):
        card = cards.box()
        title = card.row(align=True)
        name = Path(filename).name
        title.label(text='Primary' if index == 0 else name, translate=False)
        title.operator('easykig.set_reference', text='', icon='X').remove_index = index
        scale = max(2.5, min(4.3, (width - 70) / 45)) if columns == 2 else 6.5
        if not _thumbnail_row(card, context, owner, prop, filename, scale=scale):
            card.label(text='Preview unavailable', icon='IMAGE_DATA')
        if index == 0:
            card.label(text=name, translate=False)


class EASYKIG_PT_main(bpy.types.Panel):
    bl_label = 'EasyKig'
    bl_idname = 'EASYKIG_PT_main'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'EasyKig'

    def draw(self, context):
        settings = context.scene.easykig_settings
        layout = self.layout

        _draw_references(layout, settings, context)

        header, inputs = layout.panel('EASYKIG_reference_inputs', default_closed=True)
        header.label(text='Supporting Images')
        if inputs:
            inputs.label(text='Expression: Head, Design, Product')
            inputs.prop(settings, 'expression_image', text='')
            inputs.label(text='Color Palette: Head')
            inputs.prop(settings, 'character_image', text='')
            inputs.label(text='Shell Style: Design, Product')
            inputs.prop(settings, 'shell_example_image', text='')

        draw_prompt(layout, context, settings)
        actions = layout.column(align=True)
        row = actions.row(align=True)
        head = row.row(align=True)
        head.enabled = bool(settings.reference_image)
        head.operator('easykig.reference_design', text='Head').stage = 'head'
        design = row.row(align=True)
        design.enabled = bool(settings.reference_image or settings.last_head_png)
        design.operator('easykig.reference_design', text='Design').stage = 'design'
        product = row.row(align=True)
        product.enabled = bool(settings.last_design_png)
        product.operator('easykig.reference_design', text='Product').stage = 'product'

        row = actions.row(align=True)
        has_face = bool(settings.face and settings.face.type == 'MESH')
        white = row.row(align=True)
        white.enabled = has_face
        white.operator('easykig.render_white', text='White Clay')
        finish = row.row(align=True)
        finish.enabled = has_face or bool(settings.last_white_png)
        finish.operator('easykig.render_finished', text='Finish', icon='RENDER_STILL')

        result = layout.box()
        result.prop(settings, 'result_view')
        path = getattr(settings, f'last_{settings.result_view}_png')
        if not _thumbnail_row(result, context, settings, 'result_thumbnail', path):
            result.label(text='No preview for this stage', icon='IMAGE_DATA')
        layout.label(text='Design prototype only', icon='INFO')


class EASYKIG_PT_mesh_generation(bpy.types.Panel):
    bl_label = 'Manual 3D Editing'
    bl_idname = 'EASYKIG_PT_mesh_generation'
    bl_parent_id = 'EASYKIG_PT_main'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'EasyKig'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        settings = context.scene.easykig_settings
        layout = self.layout
        inputs = layout.column(align=True)
        inputs.enabled = not settings.mesh_job_running
        inputs.prop(settings, 'face', text='Source Mesh')
        inputs.operator('easykig.pick_face', text='Use Selected Mesh')
        inputs.prop(settings, 'mesh_edit_source')
        if settings.mesh_edit_source == 'file':
            inputs.prop(settings, 'mesh_edit_image', text='')
        else:
            path = target_image(settings)
            inputs.label(text=Path(path).name if path else 'Generate or choose a target image first', icon='IMAGE_DATA')
        _draw_mesh_job(layout, context, settings, ready=bool(settings.face))


def _draw_mesh_job(layout, context, job, *, ready, part=''):
    settings = context.scene.easykig_settings
    header, options = layout.panel('EASYKIG_component_sampling' if part else 'EASYKIG_mesh_options', default_closed=True)
    header.label(text='Sampling Options')
    if options:
        options.enabled = not settings.mesh_job_running
        options.prop(settings, 'mesh_edit_seed')
        options.prop(settings, 'mesh_edit_steps')
        options.prop(settings, 'mesh_edit_resolution')
    row = layout.row(align=True)
    start = row.row(align=True)
    start.enabled = not settings.mesh_job_running and ready and context.mode == 'OBJECT'
    start.operator('easykig.remote_mesh_edit', text='Edit Part in 3D' if part else 'Generate Edited 3D', icon='MESH_DATA').part = part
    resume = row.row(align=True)
    resume.enabled = not settings.mesh_job_running
    resume.operator('easykig.resume_mesh_job', text='Resume Task').part = part
    if settings.mesh_job_running:
        layout.operator('easykig.stop_mesh_wait', icon='PAUSE')
    if job.mesh_job_status != 'idle' or job.mesh_job_id:
        layout.label(text='Status: ' + job.mesh_job_status)
    if job.mesh_job_id:
        layout.prop(job, 'mesh_job_id', text='Task ID')
    if job.mesh_job_message:
        for line in job.mesh_job_message.splitlines()[:3]:
            layout.label(text=line[:110])
    if job.mesh_result_glb:
        layout.operator('easykig.import_mesh_result', text='Import Saved Result', icon='IMPORT').part = part


class EASYKIG_PT_components(bpy.types.Panel):
    bl_label = 'Component Editing'
    bl_idname = 'EASYKIG_PT_components'
    bl_parent_id = 'EASYKIG_PT_main'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'EasyKig'
    bl_order = 0

    def draw(self, context):
        settings = context.scene.easykig_settings
        identifier = settings.component
        part = component_state(settings, identifier)
        layout = self.layout
        inputs = layout.column(align=True)
        inputs.enabled = not settings.mesh_job_running
        if settings.include_rigid_hair:
            inputs.prop(settings, 'component')
        else:
            choices = inputs.row(align=True)
            choices.prop_enum(settings, 'component', 'front_face')
            choices.prop_enum(settings, 'component', 'hair_accessory')
        inputs.prop(settings, 'include_rigid_hair')

        fields = inputs.column(align=True)
        fields.use_property_split = True
        fields.use_property_decorate = False
        fields.prop(settings, 'component_product_image')
        if not settings.component_product_image:
            inputs.label(text='Using Product result' if settings.last_product_png else 'Generate Product or choose an image',
                         icon='IMAGE_DATA')
        fields.prop(part, 'notes')
        source = component_template(context, identifier)
        fields.prop(part, 'source_mesh')
        if source is not None and part.source_mesh is None:
            inputs.label(text=source.name, translate=False, icon='MESH_DATA')

        steps = inputs.column(align=True)
        isolate = steps.row()
        isolate.enabled = bool(settings.component_product_image or settings.last_product_png)
        isolate.operator('easykig.component_image', text='Generate Part Reference', icon='IMAGE_DATA').adapt = False
        adapt = steps.row()
        adapt.enabled = bool(part.reference_png and source) and context.mode == 'OBJECT'
        adapt.operator('easykig.component_image', text='Edit Part Image', icon='RENDER_STILL').adapt = True
        paths = (('Part Reference', 'reference_thumbnail', part.reference_png),
                 ('ShapeUp Target', 'target_thumbnail', part.target_png))
        width = context.region.width / context.preferences.system.ui_scale
        previews = layout.grid_flow(columns=2 if width >= 230 else 1, row_major=True, even_columns=True)
        for name, property_name, path in paths:
            if path:
                card = previews.box()
                card.label(text=name)
                if not _thumbnail_row(card, context, part, property_name, path, scale=min(5, max(2.5, (width - 65) / 47))):
                    card.label(text='Preview unavailable', icon='ERROR')
        ready = bool(part.source_mesh and part.target_png and part.source_glb)
        _draw_mesh_job(layout, context, part, part=identifier, ready=ready)


class EASYKIG_PT_modeling(bpy.types.Panel):
    bl_label = 'Modeling Tools'
    bl_idname = 'EASYKIG_PT_modeling'
    bl_parent_id = 'EASYKIG_PT_main'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'EasyKig'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        settings = context.scene.easykig_settings
        layout = self.layout

        template = layout.column(align=True)
        row = template.row(align=True)
        row.operator('easykig.create_demo', text='Demo Template')
        row.operator('easykig.pick_face', text='Use Selected')
        template.prop(settings, 'face')
        template.prop(settings, 'template_collection')

        header, importer = layout.panel('EASYKIG_model_import', default_closed=True)
        header.label(text='PMX and Material Prep')
        if importer:
            importer.prop(settings, 'pmx_meters_per_unit')
            importer.operator('easykig.import_pmx', icon='IMPORT')
            importer.operator('easykig.guess_face', text='Guess Face Mesh')
            importer.operator('easykig.split_materials', text='Split By Material (Copy)')
            importer.operator('easykig.make_working_copy', text='Bake Working Copy')

        obj = settings.face
        if obj and obj.type == 'MESH' and obj.data.shape_keys:
            header, morphs = layout.panel('EASYKIG_model_morphs')
            header.label(text='Shape Keys')
            if morphs:
                keys = obj.data.shape_keys
                if keys.use_relative:
                    for key in keys.key_blocks[1:]:
                        morphs.prop(key, 'value', text=key.name, slider=True)
                else:
                    morphs.prop(keys, 'eval_time', text='Evaluation Time')

        header, tools = layout.panel('EASYKIG_model_geometry', default_closed=True)
        header.label(text='Geometry and Export')
        if tools:
            tools.operator('easykig.set_units')
            tools.prop(settings, 'height_mm')
            tools.operator('easykig.resize_height')
            tools.prop(settings, 'shell_thickness_mm')
            tools.operator('easykig.add_solidify')
            tools.operator('easykig.basic_mesh_check')
            tools.operator('easykig.export_stl', icon='EXPORT')

        remote = layout.column(align=True)
        remote.prop(settings, 'editing_prompt', text='Edit Prompt')
        remote.operator('easykig.ai_morph', text='Apply to Shape Keys')


def register():
    image_preview.register()
    bpy.utils.register_class(EASYKIG_PT_main)
    bpy.utils.register_class(EASYKIG_PT_components)
    bpy.utils.register_class(EASYKIG_PT_mesh_generation)
    bpy.utils.register_class(EASYKIG_PT_modeling)


def unregister():
    bpy.utils.unregister_class(EASYKIG_PT_modeling)
    bpy.utils.unregister_class(EASYKIG_PT_mesh_generation)
    bpy.utils.unregister_class(EASYKIG_PT_components)
    bpy.utils.unregister_class(EASYKIG_PT_main)
    image_preview.unregister()
