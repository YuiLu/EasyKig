"""Blender UI for image-conditioned, resumable 3D edits."""
import base64
import datetime
import json
from pathlib import Path
import queue
import tempfile
import uuid

import bpy
from mathutils import Matrix

from .mesh_jobs import MeshJobClient, MeshJobWorker
from .mesh_ops import evaluated_copy, rank_face_objects
from .operators import _face, _notify_failure, _prefs
from .preview_ops import output_folder
from .remote import encode_png

_ACTIVE = None


def target_image(settings):
    fields = {'finished': 'last_finished_png', 'design': 'last_design_png',
              'product': 'last_product_png', 'head': 'last_head_png',
              'reference': 'reference_image', 'file': 'mesh_edit_image'}
    return getattr(settings, fields[settings.mesh_edit_source])


def export_source(context, obj, filepath):
    """Export a baked temporary copy so current morphs reach the 3D model."""
    if context.mode != 'OBJECT':
        raise ValueError('Switch to Object Mode before starting a 3D edit')
    old_selection = list(context.selected_objects)
    old_active = context.view_layer.objects.active
    working = None
    try:
        working = evaluated_copy(context, obj, name='EasyKig Upload Copy')
        # glTF is in metres. Blender's exporter keeps raw scene coordinates,
        # while its importer converts metres using scale_length. Bake the scene
        # unit into this temporary copy to avoid a 1000x jump in mm projects.
        working.matrix_world = Matrix.Scale(context.scene.unit_settings.scale_length, 4) @ working.matrix_world
        bpy.ops.object.select_all(action='DESELECT')
        working.select_set(True)
        context.view_layer.objects.active = working
        result = bpy.ops.export_scene.gltf(filepath=str(filepath), export_format='GLB',
                                          use_selection=True, export_apply=True, export_morph=False)
        if 'FINISHED' not in result:
            raise RuntimeError('GLB export was cancelled')
    finally:
        if working is not None:
            mesh = working.data
            bpy.data.objects.remove(working, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        bpy.ops.object.select_all(action='DESELECT')
        for item in old_selection:
            if item.name in bpy.data.objects:
                item.select_set(True)
        if old_active and old_active.name in bpy.data.objects:
            context.view_layer.objects.active = old_active


def import_result(context, filepath):
    if context.mode != 'OBJECT':
        raise ValueError('Switch to Object Mode to import the finished 3D result')
    existing = set(bpy.data.objects)
    result = bpy.ops.import_scene.gltf(filepath=str(filepath))
    if 'FINISHED' not in result:
        raise RuntimeError('Blender could not import the returned GLB')
    imported = list(set(bpy.data.objects) - existing)
    for item in imported:
        if item.type == 'MESH':
            item['easykig_role'] = 'remote_edited_mesh'
    ranked = rank_face_objects(imported)
    if not ranked:
        raise ValueError('Returned GLB contains no mesh')
    context.scene.easykig_settings.face = ranked[0]
    return imported


class _MeshModal:
    def _start(self, context, payload=None, job_id=None):
        global _ACTIVE
        if _ACTIVE is not None:
            raise ValueError('A 3D request is already being monitored')
        if not bpy.app.online_access:
            raise ValueError('Enable Allow Online Access in Blender Preferences')
        prefs = _prefs(context)
        self._scene = context.scene
        self._cleaned = False
        settings = self._scene.easykig_settings
        folder = Path(output_folder(settings))
        client = MeshJobClient(prefs.server_url, prefs.server_token, prefs.timeout_seconds)
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6]
        self._worker = MeshJobWorker(client, folder / f'edited_{stamp}.glb', folder / 'mesh_job.json',
                                     total_timeout=prefs.mesh_timeout_seconds)
        if payload is not None:
            settings.mesh_job_id = ''
            settings.mesh_result_glb = ''
            self._worker.receipt_path.write_text(json.dumps({'server_url': client.url, 'id': None}))
        settings.mesh_job_running = True
        settings.mesh_job_status = 'submitting' if payload is not None else 'resuming'
        settings.mesh_job_message = 'Esc / Stop Waiting pauses monitoring; the server task continues.'
        self._timer = context.window_manager.event_timer_add(.25, window=context.window)
        self._wm = context.window_manager
        self._wm.progress_begin(0, 100)
        _ACTIVE = self
        self._worker.start(payload, job_id)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _cleanup(self):
        global _ACTIVE
        if self._cleaned:
            return
        self._cleaned = True
        self._worker.stop.set()
        try:
            self._wm.event_timer_remove(self._timer)
            self._wm.progress_end()
        except (ReferenceError, RuntimeError):
            pass
        try:
            self._scene.easykig_settings.mesh_job_running = False
        except (ReferenceError, AttributeError):
            pass
        if _ACTIVE is self:
            _ACTIVE = None

    def _pause(self):
        if self._cleaned:
            return {'CANCELLED'}
        try:
            settings = self._scene.easykig_settings
            settings.mesh_job_status = 'paused'
            settings.mesh_job_message = ('Monitoring paused. The server task continues; use Resume Task to fetch its result.'
                if settings.mesh_job_id else 'Monitoring paused. Accepted work may continue; check the preview folder or resume with its task ID.')
        except (ReferenceError, AttributeError):
            pass
        self._cleanup()
        return {'CANCELLED'}

    def modal(self, context, event):
        if event.type == 'ESC' or self._worker.stop.is_set():
            return self._pause()
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        try:
            settings = self._scene.easykig_settings
            while True:
                kind, value = self._worker.events.get_nowait()
                if kind == 'submitted':
                    settings.mesh_job_id = value
                    settings.mesh_job_status = 'queued'
                elif kind == 'status':
                    settings.mesh_job_status = value
                    self._wm.progress_update({'queued': 20, 'running': 45, 'succeeded': 80, 'downloading': 85}.get(value, 10))
                elif kind == 'done':
                    settings.mesh_result_glb = value
                    settings.mesh_job_status = 'succeeded'
                    settings.mesh_job_message = 'Result saved. Original mesh preserved.'
                    if context.scene == self._scene and context.mode == 'OBJECT':
                        imported = import_result(context, value)
                        self.report({'INFO'}, f'3D edit imported {len(imported)} object(s); original intact')
                    else:
                        self.report({'INFO'}, '3D edit saved. Return to the source scene in Object Mode and click Import Result.')
                    self._cleanup()
                    return {'FINISHED'}
                elif kind == 'error':
                    settings.mesh_job_status = ('paused' if settings.mesh_job_id and settings.mesh_job_status != 'failed' else 'failed')
                    settings.mesh_job_message = value[:2000]
                    self._cleanup()
                    return _notify_failure(self, RuntimeError(value))
        except queue.Empty:
            pass
        except Exception as exc:
            self._cleanup()
            return _notify_failure(self, exc)
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
        return {'PASS_THROUGH'}

    def cancel(self, context):
        self._pause()


class EASYKIG_OT_remote_mesh_edit(_MeshModal, bpy.types.Operator):
    bl_idname = 'easykig.remote_mesh_edit'
    bl_label = 'Generate Edited 3D Mesh'
    bl_description = 'Upload the baked source mesh and target image; monitor without blocking Blender'

    def execute(self, context):
        try:
            if _ACTIVE is not None:
                raise ValueError('A 3D request is already being monitored')
            settings = context.scene.easykig_settings
            image_path = target_image(settings)
            image = encode_png(bpy.path.abspath(image_path)) if image_path else None
            with tempfile.TemporaryDirectory(prefix='easykig_upload_') as temp:
                path = Path(temp) / 'source.glb'
                export_source(context, _face(context), path)
                raw = path.read_bytes()
            if len(raw) > 20 * 1024 * 1024:
                raise ValueError('Mesh GLB is over 20 MiB; simplify before uploading')
            payload = {'prompt': settings.editing_prompt, 'mesh_glb_base64': base64.b64encode(raw).decode('ascii'),
                       'seed': settings.mesh_edit_seed, 'steps': settings.mesh_edit_steps,
                       'watertight_resolution': int(settings.mesh_edit_resolution)}
            if image:
                payload['edit_png_base64'] = image
            return self._start(context, payload=payload)
        except Exception as exc:
            return _notify_failure(self, exc)


class EASYKIG_OT_resume_mesh_job(_MeshModal, bpy.types.Operator):
    bl_idname = 'easykig.resume_mesh_job'
    bl_label = 'Resume Task'
    bl_description = 'Resume monitoring a submitted 3D job, without another GPU generation'

    def execute(self, context):
        try:
            settings = context.scene.easykig_settings
            job_id = settings.mesh_job_id.strip()
            if not job_id:
                receipt_path = Path(output_folder(settings)) / 'mesh_job.json'
                if not receipt_path.exists():
                    raise ValueError('No saved 3D task. Start a new edit first.')
                receipt = json.loads(receipt_path.read_text())
                client = MeshJobClient(_prefs(context).server_url, _prefs(context).server_token)
                if receipt['server_url'] != client.url:
                    raise ValueError('Saved task belongs to a different EasyKig server')
                job_id = receipt['id']
                if not job_id:
                    raise ValueError('No task ID has been received yet. Retry after the upload completes.')
            job_id = MeshJobWorker.job_id(job_id)
            settings.mesh_job_id = job_id
            return self._start(context, job_id=job_id)
        except Exception as exc:
            return _notify_failure(self, exc)


class EASYKIG_OT_stop_mesh_wait(bpy.types.Operator):
    bl_idname = 'easykig.stop_mesh_wait'
    bl_label = 'Stop Waiting'
    bl_description = 'Pause monitoring; the server task continues and can be resumed'

    def execute(self, context):
        if _ACTIVE is not None:
            _ACTIVE._worker.stop.set()
        return {'FINISHED'}


class EASYKIG_OT_import_mesh_result(bpy.types.Operator):
    bl_idname = 'easykig.import_mesh_result'
    bl_label = 'Import Result'

    def execute(self, context):
        try:
            import_result(context, bpy.path.abspath(context.scene.easykig_settings.mesh_result_glb))
            return {'FINISHED'}
        except Exception as exc:
            return _notify_failure(self, exc)


_CLASSES = (EASYKIG_OT_remote_mesh_edit, EASYKIG_OT_resume_mesh_job,
            EASYKIG_OT_stop_mesh_wait, EASYKIG_OT_import_mesh_result)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    if _ACTIVE is not None:
        _ACTIVE._worker.stop.set()
        _ACTIVE._cleanup()
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
