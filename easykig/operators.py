import base64
import datetime
from pathlib import Path
import tempfile
import bpy
from bpy.props import StringProperty
from bpy_extras.io_utils import ImportHelper, ExportHelper
from .mesh_ops import (
    evaluated_copy, ensure_mm_scene, get_shape_key_ranges, get_shape_key_values,
    make_demo_template, rank_face_objects, set_shape_key_values, split_copy_by_material,
)
from .preview_ops import output_folder, white_render
from .remote import encode_png, request_json, save_b64_png


def _settings(context):
    return context.scene.easykig_settings


def _prefs(context):
    key=__package__
    addon=context.preferences.addons.get(key)
    if addon is None:
        raise RuntimeError('EasyKig preferences not found; enable the add-on')
    return addon.preferences


def _face(context):
    obj=_settings(context).face
    if not obj or obj.type != 'MESH':
        raise RuntimeError('Choose a Mesh in Face / Template')
    return obj


def _notify_failure(op, exc):
    op.report({'ERROR'}, str(exc)[:350])
    return {'CANCELLED'}


class EASYKIG_OT_import_pmx(bpy.types.Operator, ImportHelper):
    bl_idname = 'easykig.import_pmx'
    bl_label = 'Import PMX (minimal)'
    bl_description = 'Calls installed MMD Tools PMX importer; no animation/physics UI exposed'
    filename_ext='.pmx'
    filter_glob: StringProperty(default='*.pmx;*.pmd', options={'HIDDEN'})

    def execute(self, context):
        try:
            if 'import_model' not in dir(bpy.ops.mmd_tools):
                raise RuntimeError('MMD Tools is missing/disabled. Install MMD Tools v4.x first.')
            importer = bpy.ops.mmd_tools.import_model
            if not importer.poll():
                raise RuntimeError('Switch to Object Mode before importing PMX')
            existing=set(bpy.data.objects)
            settings = _settings(context)
            scale = settings.pmx_meters_per_unit / context.scene.unit_settings.scale_length
            result = importer('EXEC_DEFAULT', filepath=self.filepath, scale=scale,
                              types={'MESH', 'ARMATURE', 'MORPHS'})
            if 'FINISHED' not in result:
                raise RuntimeError('MMD Tools cancelled the import')
            incoming=list(set(bpy.data.objects)-existing)
            if not any(o.type == 'MESH' for o in incoming):
                raise RuntimeError('MMD Tools did not import a mesh')
            for o in incoming:
                if o.type=='MESH':
                    o['easykig_role']='imported_game_mesh'
            ranked=rank_face_objects(incoming)
            if ranked:
                _settings(context).face=ranked[0]
            self.report({'INFO'},f'Imported {len(incoming)} objects; inspect face selection')
            return {'FINISHED'}
        except Exception as exc:
            return _notify_failure(self,exc)


class EASYKIG_OT_pick_face(bpy.types.Operator):
    bl_idname='easykig.pick_face'
    bl_label='Use Selected Mesh as Face'
    def execute(self,context):
        selected=context.active_object
        if not selected or selected.type!='MESH':
            return _notify_failure(self,ValueError('Select a Mesh object first'))
        _settings(context).face=selected
        return {'FINISHED'}


class EASYKIG_OT_guess_face(bpy.types.Operator):
    bl_idname='easykig.guess_face'
    bl_label='Guess Face by Mesh/Material Name'
    def execute(self,context):
        ranked=rank_face_objects(context.selected_objects or context.scene.objects)
        if not ranked:
            return _notify_failure(self,ValueError('No meshes found'))
        _settings(context).face=ranked[0]
        self.report({'INFO'},f'Guess: {ranked[0].name}. Verify manually.')
        return {'FINISHED'}


class EASYKIG_OT_split_materials(bpy.types.Operator):
    bl_idname='easykig.split_materials'
    bl_label='Split Working Copy by Material'
    bl_description='Bakes active deformation into a copy, then separates by material; source unchanged'
    def execute(self,context):
        try:
            parts=split_copy_by_material(context,_face(context))
            ranked=rank_face_objects(parts)
            if ranked:
                _settings(context).face=ranked[0]
            self.report({'INFO'},f'Split {len(parts)} material parts from a new baked copy')
            return {'FINISHED'}
        except Exception as exc:
            return _notify_failure(self,exc)


class EASYKIG_OT_make_working_copy(bpy.types.Operator):
    bl_idname='easykig.make_working_copy'
    bl_label='Bake Working Face Copy'
    def execute(self,context):
        try:
            copy=evaluated_copy(context,_face(context))
            _settings(context).face=copy
            self.report({'INFO'},'Created baked working copy; original kept intact')
            return {'FINISHED'}
        except Exception as exc:
            return _notify_failure(self,exc)


class EASYKIG_OT_create_demo(bpy.types.Operator):
    bl_idname='easykig.create_demo'
    bl_label='Create Kig Demo Template'
    bl_description='Demo morphable head; NOT a validated manufacturable mask'
    def execute(self,context):
        try:
            template=make_demo_template(context)
            _settings(context).face=template
            self.report({'INFO'},'Created demo template with 8 Shape Keys (not print-ready)')
            return {'FINISHED'}
        except Exception as exc:
            return _notify_failure(self,exc)


class EASYKIG_OT_set_units(bpy.types.Operator):
    bl_idname='easykig.set_units'
    bl_label='Set Scene to Millimeters'
    def execute(self,context):
        ensure_mm_scene(context.scene)
        return {'FINISHED'}


class EASYKIG_OT_resize_height(bpy.types.Operator):
    bl_idname='easykig.resize_height'
    bl_label='Scale Face to Target Height'
    bl_description='Uniformly scale selected face only; preserve proportions and source mesh'
    def execute(self,context):
        try:
            obj=_face(context)
            if obj.dimensions.z<=0:
                raise ValueError('Mesh height is zero')
            target=_settings(context).height_mm*.001/context.scene.unit_settings.scale_length
            factor=target/obj.dimensions.z
            obj.scale = tuple(value*factor for value in obj.scale)
            self.report({'INFO'},f'Uniformly scaled {obj.name} to target height')
            return {'FINISHED'}
        except Exception as exc:
            return _notify_failure(self,exc)


class EASYKIG_OT_basic_mesh_check(bpy.types.Operator):
    bl_idname='easykig.basic_mesh_check'
    bl_label='Check Non-manifold / Loose Geometry'
    bl_description='Basic topology check after modifiers (does not certify manufacturability)'
    def execute(self,context):
        import bmesh
        try:
            obj=_face(context)
            depsgraph=context.evaluated_depsgraph_get()
            evaluated=obj.evaluated_get(depsgraph)
            mesh=bpy.data.meshes.new_from_object(evaluated,preserve_all_data_layers=True,depsgraph=depsgraph)
            bm=bmesh.new()
            try:
                bm.from_mesh(mesh)
                bad=sum(1 for e in bm.edges if not e.is_manifold)
                loose=sum(1 for v in bm.verts if not v.link_edges)
                degenerate=sum(1 for f in bm.faces if f.calc_area()<=1e-10)
            finally:
                bm.free()
                bpy.data.meshes.remove(mesh)
            flags={'WARNING'} if (bad or loose or degenerate) else {'INFO'}
            self.report(flags,f'non-manifold edges={bad}; loose verts={loose}; degenerate faces={degenerate}')
            return {'FINISHED'}
        except Exception as exc:
            return _notify_failure(self,exc)


class EASYKIG_OT_add_solidify(bpy.types.Operator):
    bl_idname='easykig.add_solidify'
    bl_label='Add Non-destructive Shell Thickness'
    bl_description='Preview thickness via Solidify. Not a manufacturing validation.'
    def execute(self,context):
        try:
            obj=_face(context)
            settings=_settings(context)
            # For scene scale_length=.001, one Blender unit is one millimeter.
            mm_to_bu=(0.001/context.scene.unit_settings.scale_length)
            modifier=next((m for m in obj.modifiers if m.name=='EasyKig Thickness'),None)
            if modifier is None:
                modifier=obj.modifiers.new('EasyKig Thickness','SOLIDIFY')
            modifier.thickness=settings.shell_thickness_mm*mm_to_bu
            modifier.offset=-1
            modifier.use_even_offset=True
            self.report({'WARNING'},'Added thickness modifier only; inspect overlaps and intentional openings')
            return {'FINISHED'}
        except Exception as exc:
            return _notify_failure(self,exc)


class EASYKIG_OT_export_stl(bpy.types.Operator,ExportHelper):
    bl_idname='easykig.export_stl'
    bl_label='Export Selected Face STL (Experimental)'
    filename_ext='.stl'
    filter_glob: StringProperty(default='*.stl',options={'HIDDEN'})
    def execute(self,context):
        try:
            obj=_face(context)
            old_selection=list(context.selected_objects)
            old_active=context.view_layer.objects.active
            try:
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                context.view_layer.objects.active=obj
                if 'stl_export' in dir(bpy.ops.wm):
                    result = bpy.ops.wm.stl_export(filepath=self.filepath,export_selected_objects=True,apply_modifiers=True,use_scene_unit=True,global_scale=1000)
                else:
                    result = bpy.ops.export_mesh.stl(filepath=self.filepath,use_selection=True,use_scene_unit=True,global_scale=1000)
                if 'FINISHED' not in result:
                    raise RuntimeError('STL export was cancelled')
            finally:
                bpy.ops.object.select_all(action='DESELECT')
                for selected in old_selection:
                    if selected.name in bpy.data.objects:
                        selected.select_set(True)
                if old_active and old_active.name in bpy.data.objects:
                    context.view_layer.objects.active=old_active
            self.report({'WARNING'},'STL exported: manifold, wall thickness, eye holes and scale need validation')
            return {'FINISHED'}
        except Exception as exc:
            return _notify_failure(self,exc)


class EASYKIG_OT_health(bpy.types.Operator):
    bl_idname='easykig.health'
    bl_label='Test Remote Server'
    def execute(self,context):
        try:
            r=request_json(_prefs(context),'/health')
            self.report({'INFO'},f"Server: {r.get('name','unknown')} / {r.get('status','unknown')}")
            return {'FINISHED'}
        except Exception as exc:
            return _notify_failure(self,exc)


class EASYKIG_OT_ai_morph(bpy.types.Operator):
    bl_idname='easykig.ai_morph'
    bl_label='Remote Text → Shape Keys'
    bl_description='Sends only shape key names/values and instruction, not the private mesh'
    def execute(self,context):
        try:
            obj=_face(context)
            current=get_shape_key_values(obj)
            if not current:
                raise ValueError('This template has no Shape Keys; use the demo template or add your own')
            if not obj.data.shape_keys.use_relative:
                raise ValueError('Text editing requires relative Shape Keys. Use Evaluation Time for this template.')
            response=request_json(_prefs(context),'/v1/edit/parameters',{
                'prompt': _settings(context).editing_prompt,
                'shape_keys': current,
                'ranges': get_shape_key_ranges(obj),
            })
            count=set_shape_key_values(obj,response.get('shape_keys',{}))
            note=response.get('message','')
            self.report({'INFO'},f'Applied {count} value(s). {note[:120]}')
            return {'FINISHED'}
        except Exception as exc:
            return _notify_failure(self,exc)


class EASYKIG_OT_reference_design(bpy.types.Operator):
    bl_idname='easykig.reference_design'
    bl_label='AI Character → Kig Design Reference'
    bl_description='Use an image-edit provider to prepare head or kigurumi design reference sheets'
    stage: StringProperty(default='head')
    def execute(self,context):
        try:
            s=_settings(context)
            outputs = {
                'head': ('last_head_png', 'head_reference.png'),
                'design': ('last_design_png', 'kig_design.png'),
                'product': ('last_product_png', 'product_reference.png'),
            }
            reference = bpy.path.abspath(s.reference_image) if s.reference_image else ''
            source = {'head': reference, 'design': s.last_head_png or reference,
                      'product': s.last_design_png}.get(self.stage)
            if not source:
                raise ValueError('Generate Kig Design first' if self.stage == 'product' else 'Choose Reference Image first')
            supporting = {
                'head': (s.expression_image, s.character_image),
                'design': (s.expression_image, s.shell_example_image),
                'product': (s.shell_example_image, s.expression_image),
            }[self.stage]
            result=request_json(_prefs(context),'/v1/reference/transform',{
                'source_png_base64':encode_png(source),
                'stage':self.stage,
                'prompt':s.finishing_prompt,
                'additional_png_base64': [encode_png(bpy.path.abspath(path)) for path in supporting if path],
            })
            output_property, filename = outputs[self.stage]
            dest=str(Path(output_folder(s))/filename)
            save_b64_png(result['image_png_base64'],dest)
            setattr(s, output_property, dest)
            if self.stage == 'head':
                s.last_design_png = ''
            if self.stage in ('head', 'design'):
                s.last_product_png = ''
            self.report({'INFO'},f'Design reference saved: {dest}')
            return {'FINISHED'}
        except Exception as exc:
            return _notify_failure(self,exc)


class EASYKIG_OT_render_white(bpy.types.Operator):
    bl_idname='easykig.render_white'
    bl_label='Render White Clay Preview'
    def execute(self,context):
        try:
            path=white_render(context,_face(context))
            self.report({'INFO'},f'White render: {path}')
            return {'FINISHED'}
        except Exception as exc:
            return _notify_failure(self,exc)


class EASYKIG_OT_render_finished(bpy.types.Operator):
    bl_idname='easykig.render_finished'
    bl_label='AI White → Finished Preview'
    bl_description='Uploads current white render to configured remote server and image provider'
    def execute(self,context):
        try:
            settings=_settings(context)
            source=settings.last_white_png
            if not source or not Path(source).exists():
                source=white_render(context,_face(context))
            data={'white_png_base64':encode_png(source),'prompt':settings.finishing_prompt}
            if settings.reference_image:
                ref=bpy.path.abspath(settings.reference_image)
                data['reference_png_base64']=encode_png(ref)
            result=request_json(_prefs(context),'/v1/preview/finish',data)
            filepath=str(Path(output_folder(settings))/('finished_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.png'))
            save_b64_png(result['image_png_base64'],filepath)
            settings.last_finished_png=filepath
            self.report({'INFO'},f'AI design preview saved: {filepath}')
            return {'FINISHED'}
        except Exception as exc:
            return _notify_failure(self,exc)


class EASYKIG_OT_open_image(bpy.types.Operator):
    bl_idname='easykig.open_image'
    bl_label='Open Preview Image'
    kind: StringProperty(default='finished')
    def execute(self,context):
        path = getattr(_settings(context), {
            'head': 'last_head_png', 'design': 'last_design_png',
            'product': 'last_product_png', 'white': 'last_white_png',
            'finished': 'last_finished_png',
        }[self.kind])
        if not path or not Path(path).exists():
            return _notify_failure(self,ValueError('Generate the preview first'))
        bpy.ops.wm.path_open(filepath=path)
        return {'FINISHED'}


class EASYKIG_OT_remote_mesh_edit(bpy.types.Operator):
    bl_idname='easykig.remote_mesh_edit'
    bl_label='Send Mesh to Remote 3D Editor'
    bl_description='Explicitly upload selected mesh as GLB, import the edited GLB as a new object'
    def execute(self,context):
        try:
            obj=_face(context)
            old_selection=list(context.selected_objects)
            old_active=context.view_layer.objects.active
            with tempfile.TemporaryDirectory(prefix='easykig_remote_') as tmp:
                upload=str(Path(tmp)/'input.glb')
                local=str(Path(tmp)/'output.glb')
                try:
                    bpy.ops.object.select_all(action='DESELECT')
                    obj.select_set(True)
                    context.view_layer.objects.active=obj
                    result = bpy.ops.export_scene.gltf(filepath=upload,export_format='GLB',use_selection=True,export_apply=True)
                    if 'FINISHED' not in result:
                        raise RuntimeError('GLB export was cancelled')
                finally:
                    bpy.ops.object.select_all(action='DESELECT')
                    for item in old_selection:
                        if item.name in bpy.data.objects:
                            item.select_set(True)
                    if old_active and old_active.name in bpy.data.objects:
                        context.view_layer.objects.active=old_active
                raw=Path(upload).read_bytes()
                if len(raw)>20*1024*1024:
                    raise ValueError('Mesh GLB is over 20 MB; simplify before uploading')
                result=request_json(_prefs(context),'/v1/edit3d',{
                    'prompt':_settings(context).editing_prompt,
                    'mesh_glb_base64':base64.b64encode(raw).decode('ascii'),
                })
                glb=base64.b64decode(result['mesh_glb_base64'],validate=True)
                if not glb.startswith(b'glTF'):
                    raise ValueError('Remote server did not return a GLB')
                Path(local).write_bytes(glb)
                existing=set(bpy.data.objects)
                result = bpy.ops.import_scene.gltf(filepath=local)
                if 'FINISHED' not in result:
                    raise RuntimeError('Blender could not import the returned GLB')
                imported=list(set(bpy.data.objects)-existing)
                for candidate in imported:
                    if candidate.type=='MESH':
                        candidate['easykig_role']='remote_edited_mesh'
                ranked=rank_face_objects(imported)
                if ranked:
                    _settings(context).face=ranked[0]
                self.report({'INFO'},f'Remote edit returned {len(imported)} object(s); original intact')
                return {'FINISHED'}
        except Exception as exc:
            return _notify_failure(self,exc)


_CLASSES = (
    EASYKIG_OT_import_pmx,EASYKIG_OT_pick_face,EASYKIG_OT_guess_face,
    EASYKIG_OT_split_materials,EASYKIG_OT_make_working_copy,EASYKIG_OT_create_demo,
    EASYKIG_OT_set_units,EASYKIG_OT_resize_height,EASYKIG_OT_basic_mesh_check,
    EASYKIG_OT_add_solidify,EASYKIG_OT_export_stl,
    EASYKIG_OT_health,EASYKIG_OT_ai_morph,EASYKIG_OT_reference_design,
    EASYKIG_OT_render_white,
    EASYKIG_OT_render_finished,EASYKIG_OT_open_image,EASYKIG_OT_remote_mesh_edit,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
