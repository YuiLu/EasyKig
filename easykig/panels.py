from pathlib import Path

import bpy
import bpy.utils.previews


_previews = None
_preview_files = {}


def _thumbnail(slot, filename):
    path = Path(bpy.path.abspath(filename)) if filename else None
    try:
        signature = (path, path.stat().st_mtime_ns) if path else None
    except OSError:
        signature = None
    if _preview_files.get(slot) != signature:
        if slot in _previews:
            del _previews[slot]
        _preview_files[slot] = signature
        if signature:
            try:
                _previews.load(slot, str(path), 'IMAGE')
            except (OSError, RuntimeError):
                pass
    return _previews[slot].icon_id if slot in _previews else 0


def _thumbnail_row(layout, slot, filename, scale):
    icon = _thumbnail(slot, filename)
    if icon:
        row = layout.row()
        row.alignment = 'CENTER'
        row.template_icon(icon_value=icon, scale=scale)


class EASYKIG_PT_main(bpy.types.Panel):
    bl_label = 'EasyKig'
    bl_idname = 'EASYKIG_PT_main'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'EasyKig'

    def draw(self, context):
        settings = context.scene.easykig_settings
        layout = self.layout

        reference = layout.box()
        reference.label(text='Reference Image')
        row = reference.row(align=True)
        row.scale_y = 1.4
        label = Path(settings.reference_image).name if settings.reference_image else 'Drop PNG or Browse'
        row.operator('easykig.set_reference', text=label, icon='FILE_IMAGE').filepath = ''
        if settings.reference_image:
            row.operator('easykig.set_reference', text='', icon='X').clear = True
            _thumbnail_row(reference, 'reference', settings.reference_image, 3.0)

        header, inputs = layout.panel('EASYKIG_reference_inputs', default_closed=True)
        header.label(text='Supporting Images')
        if inputs:
            inputs.prop(settings, 'expression_image', text='Expression')
            inputs.prop(settings, 'character_image', text='Character Colors')
            inputs.prop(settings, 'shell_example_image', text='Shell Example')

        layout.prop(settings, 'finishing_prompt', text='Prompt')
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
        _thumbnail_row(result, 'result', path, 6.0)
        if path and Path(bpy.path.abspath(path)).is_file():
            result.operator('easykig.open_image', text='Open Full Size', icon='ZOOM_IN').kind = settings.result_view
        else:
            result.label(text='No preview for this stage', icon='IMAGE_DATA')
        layout.label(text='Design prototype / 非制造级', icon='INFO')


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
    global _previews
    _previews = bpy.utils.previews.new()
    bpy.utils.register_class(EASYKIG_PT_main)
    bpy.utils.register_class(EASYKIG_PT_modeling)


def unregister():
    global _previews
    bpy.utils.unregister_class(EASYKIG_PT_modeling)
    bpy.utils.unregister_class(EASYKIG_PT_main)
    bpy.utils.previews.remove(_previews)
    _previews = None
    _preview_files.clear()
