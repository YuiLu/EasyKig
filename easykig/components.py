"""Scene state for editing independent template meshes."""

import re

import bpy
from bpy.props import EnumProperty, PointerProperty, StringProperty

from .image_preview import component_reference_items, component_target_items
from .image_prompts import COMPONENT_LABELS


_NAME_HINTS = {
    'front_face': ('face', 'frontface', 'faceplate', '前脸', '前臉', '面壳', '面殼'),
    'hair_accessory': ('hairaccessory', 'hairornament', 'hairclip', '发饰', '髮飾', '頭飾', '头饰'),
    'rigid_front_hair': ('fronthair', 'bangs', '前发', '前髮', '刘海', '瀏海'),
}


def _mesh_only(_owner, obj):
    return obj.type == 'MESH'


def clear_component_target(component, _context=None):
    component.target_png = ''
    component.source_glb = ''


def reset_components(settings, _context):
    for identifier in COMPONENT_LABELS:
        component = getattr(settings, identifier)
        component.reference_png = ''
        clear_component_target(component)


def reset_generated_components(settings, context):
    if not settings.component_product_image:
        reset_components(settings, context)


def update_rigid_hair(settings, _context):
    if not settings.include_rigid_hair and settings.component == 'rigid_front_hair':
        settings.component = 'front_face'


def component_state(settings, identifier):
    if identifier not in COMPONENT_LABELS:
        raise ValueError('Choose a component')
    if identifier == 'rigid_front_hair' and not settings.include_rigid_hair:
        raise ValueError('Enable Rigid Front Hair to edit this component')
    return getattr(settings, identifier)


def component_template(context, identifier):
    component = component_state(context.scene.easykig_settings, identifier)
    objects = context.view_layer.objects
    if component.source_mesh is not None:
        obj = component.source_mesh
        return obj if obj.type == 'MESH' and obj.name in objects else None
    candidates = []
    hints = _NAME_HINTS[identifier]
    suffixes = tuple(hint for hint in hints if hint != 'face')
    for obj in objects:
        if obj.type != 'MESH' or obj.get('easykig_role') == 'remote_edited_mesh':
            continue
        names = [re.sub(r'[^\w]+|_', ' ', name.casefold()) for name in (obj.name, obj.data.name)]
        tokens = set(' '.join(names).split())
        joined = [name.replace(' ', '') for name in names]
        if tokens.intersection(hints) or any(name.endswith(suffixes) for name in joined):
            candidates.append(obj)
    return candidates[0] if len(candidates) == 1 else None


class EASYKIG_Component(bpy.types.PropertyGroup):
    source_mesh: PointerProperty(name='Source Mesh', type=bpy.types.Object, poll=_mesh_only, update=clear_component_target)
    notes: StringProperty(name='Part Notes', maxlen=1500,
                          description='Describe the desired component, such as the blue flower on the left')
    reference_png: StringProperty(subtype='FILE_PATH')
    target_png: StringProperty(subtype='FILE_PATH')
    source_glb: StringProperty(subtype='FILE_PATH')
    reference_thumbnail: EnumProperty(items=component_reference_items, options={'SKIP_SAVE'})
    target_thumbnail: EnumProperty(items=component_target_items, options={'SKIP_SAVE'})
    mesh_job_id: StringProperty(name='3D Task ID')
    mesh_job_status: StringProperty(default='idle', options={'SKIP_SAVE'})
    mesh_job_message: StringProperty(options={'SKIP_SAVE'})
    mesh_result_glb: StringProperty(subtype='FILE_PATH')
