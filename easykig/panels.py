from pathlib import Path

import bpy

from . import image_preview
from .properties import MAX_REFERENCE_IMAGES, PROMPT_FIELDS, get_image_prompt, image_prompt_rows


def _thumbnail_row(layout, context, owner, property_name, filename, scale=7.0):
    if not image_preview.preview_icon(filename):
        return False
    row = layout.row()
    row.alignment = 'CENTER'
    ui_scale = context.preferences.system.ui_scale
    popup_scale = max(9.0, min(22.0, (context.window.height - 60) / (40 * ui_scale)))
    row.template_icon_view(owner, property_name, scale=scale, scale_popup=popup_scale)
    return True


def _draw_prompt(layout, settings):
    box = layout.box()
    header = box.row(align=True)
    header.label(text='Prompt', icon='TEXT')
    header.operator('easykig.paste_image_prompt', text='Paste', icon='PASTEDOWN')
    header.operator('easykig.paste_image_prompt', text='', icon='X').clear = True
    count = min(PROMPT_FIELDS, max(4, len(image_prompt_rows(settings)) + 1))
    fields = box.column(align=True)
    for index in range(count):
        fields.prop(settings, f'prompt_row_{index}', text='')
    length = len(get_image_prompt(settings))
    if length > 1500:
        box.label(text=f'{length:,} / 1,500 characters', icon='ERROR')


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

        _draw_prompt(layout, settings)
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
        remote.operator('easykig.remote_mesh_edit', text='Edit Mesh (GLB)')


def register():
    image_preview.register()
    bpy.utils.register_class(EASYKIG_PT_main)
    bpy.utils.register_class(EASYKIG_PT_modeling)


def unregister():
    bpy.utils.unregister_class(EASYKIG_PT_modeling)
    bpy.utils.unregister_class(EASYKIG_PT_main)
    image_preview.unregister()
