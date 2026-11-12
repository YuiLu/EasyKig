"""Headless Blender 5.1 validation against the test harness' fake ShapeUp."""
import json
import importlib
import os
from pathlib import Path
import sys
import time
import zipfile
from types import SimpleNamespace

import bpy
import addon_utils
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
folder = Path(os.environ['EASYKIG_SMOKE_DIR'])
addon_zip = os.environ.get('EASYKIG_ADDON_ZIP')
module_name = 'easykig'
if addon_zip:
    repository = folder/'extension-repository'
    package = repository/'easykig'
    package.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(addon_zip) as archive:
        archive.extractall(package)
    assert bpy.ops.preferences.extension_repo_add(name='EasyKig Smoke', type='LOCAL',
        use_custom_directory=True, custom_directory=str(repository)) == {'FINISHED'}
    repo = next(item for item in bpy.context.preferences.extensions.repos
                if Path(item.directory).resolve() == repository.resolve())
    repo.module = 'easykig_smoke'
    repo.source = 'SYSTEM'
    module_name = 'bl_ext.easykig_smoke.easykig'
assert addon_utils.enable(module_name, default_set=True) is not None
mesh_operators = importlib.import_module(module_name+'.mesh_operators')
prefs = bpy.context.preferences.addons[module_name].preferences
prefs.server_url = os.environ['EASYKIG_SMOKE_URL']
prefs.server_token = 'blender-smoke'
prefs.preview_directory = str(folder)
settings = bpy.context.scene.easykig_settings
bpy.context.scene.unit_settings.system = 'METRIC'
bpy.context.scene.unit_settings.scale_length = .001
bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8)
source = bpy.context.object
source.name = 'EasyKig Source Smoke'
source.location = (123, 45, 67)
source.scale = (100, 80, 130)
source.shape_key_add(name='Basis')
key = source.shape_key_add(name='Edited')
for vertex in key.data:
    vertex.co.z *= 1.15
key.value = .6
key_value = float(key.value)
key_coordinates = [tuple(v.co) for v in key.data]
key_names = [k.name for k in source.data.shape_keys.key_blocks]
bpy.context.view_layer.update()
evaluated = source.evaluated_get(bpy.context.evaluated_depsgraph_get())
expected = [evaluated.matrix_world @ Vector(v) for v in evaluated.bound_box]
expected_bounds = [[min(v[i] for v in expected) for i in range(3)],
                   [max(v[i] for v in expected) for i in range(3)]]
original = [tuple(v.co) for v in source.data.vertices]
settings.face = source
image = bpy.data.images.new('Target Smoke', width=8, height=8, alpha=True)
image.generated_color = (1, .8, .8, 1)
image.filepath_raw = str(folder/'target.png')
image.file_format = 'PNG'
image.save()
settings.mesh_edit_source = 'file'
settings.mesh_edit_image = image.filepath_raw
settings.mesh_edit_resolution = '128'
settings.mesh_edit_steps = 3
mesh_operators.export_source(bpy.context, source, folder/'source.glb')


def finish_modal():
    deadline = time.monotonic() + 60
    while mesh_operators._ACTIVE is not None:
        if time.monotonic() > deadline:
            raise RuntimeError('3D modal operator timed out')
        op = mesh_operators._ACTIVE
        result = op.modal(bpy.context, SimpleNamespace(type='TIMER'))
        if result == {'CANCELLED'}:
            raise RuntimeError(settings.mesh_job_message)
        time.sleep(.05)


assert bpy.ops.easykig.remote_mesh_edit() == {'RUNNING_MODAL'}
deadline = time.monotonic() + 60
while not settings.mesh_job_id:
    assert time.monotonic() < deadline, 'Job was not submitted'
    assert mesh_operators._ACTIVE is not None, settings.mesh_job_message
    mesh_operators._ACTIVE.modal(bpy.context, SimpleNamespace(type='TIMER'))
    time.sleep(.05)
assert bpy.ops.easykig.stop_mesh_wait() == {'FINISHED'}
assert mesh_operators._ACTIVE.modal(bpy.context, SimpleNamespace(type='TIMER')) == {'CANCELLED'}
assert settings.mesh_job_status == 'paused' and not settings.mesh_job_running
assert bpy.ops.easykig.resume_mesh_job() == {'RUNNING_MODAL'}
finish_modal()
assert settings.mesh_job_status == 'succeeded'
assert source.name in bpy.data.objects
assert source.data.shape_keys.key_blocks['Edited'].value == key_value
assert [tuple(v.co) for v in source.data.shape_keys.key_blocks['Edited'].data] == key_coordinates
assert [k.name for k in source.data.shape_keys.key_blocks] == key_names
assert [tuple(v.co) for v in source.data.vertices] == original
result = settings.face
assert result != source and result['easykig_role'] == 'remote_edited_mesh'
bounds = [result.matrix_world @ Vector(v) for v in result.bound_box]
actual_bounds = [[min(v[i] for v in bounds) for i in range(3)],
                 [max(v[i] for v in bounds) for i in range(3)]]
for expected_row, actual_row in zip(expected_bounds, actual_bounds):
    assert max(abs(a-b) for a,b in zip(expected_row,actual_row)) < .01, (expected_bounds,actual_bounds)
assert bpy.ops.easykig.resume_mesh_job() == {'RUNNING_MODAL'}
finish_modal()
report={'blender_version':bpy.app.version_string,'module':module_name,'job_id':settings.mesh_job_id,
        'source_shape_keys_preserved':True,'world_bounds_preserved':True,
        'result_path':settings.mesh_result_glb,'pause_succeeded':True,'resume_succeeded':True}
addon_utils.disable(module_name)
assert not hasattr(bpy.types.Scene,'easykig_settings')
(folder/'blender-smoke.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
