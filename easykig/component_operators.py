"""Generate an isolated part reference and adapt it to one template."""

from pathlib import Path
import tempfile
import uuid

import bpy
from bpy.props import BoolProperty

from .components import clear_component_target, component_state, component_template
from .image_prompts import COMPONENT_LABELS
from .mesh_operators import export_source
from .operators import _notify_failure, _request_image
from .preview_ops import output_folder
from .remote import encode_png, save_b64_png


class EASYKIG_OT_component_image(bpy.types.Operator):
    bl_idname = 'easykig.component_image'
    bl_label = 'Generate Component Image'
    adapt: BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def description(cls, _context, properties):
        if properties.adapt:
            return 'Render the isolated template and edit it with the selected part reference'
        return 'Generate a single-part product reference from the finished product image'

    def execute(self, context):
        try:
            settings = context.scene.easykig_settings
            identifier = settings.component
            part = component_state(settings, identifier)
            if settings.mesh_job_running:
                raise ValueError('Pause the current 3D task before preparing another component')
            folder = output_folder(settings) / 'parts'
            folder.mkdir(exist_ok=True)
            stem = folder / f'{identifier}_{uuid.uuid4().hex[:12]}'
            payload = {'part': identifier, 'prompt': part.notes}
            if self.adapt:
                self._adapt(context, identifier, part, payload, stem)
            else:
                product = settings.component_product_image or settings.last_product_png
                if not product:
                    raise ValueError('Generate Product or choose an existing Product Image first')
                payload['source_png_base64'] = encode_png(bpy.path.abspath(product))
                result = _request_image(context, '/v1/components/reference', payload)
                path = stem.with_suffix('.png')
                save_b64_png(result['image_png_base64'], path)
                part.reference_png = str(path)
                clear_component_target(part)
            self.report({'INFO'}, f'{COMPONENT_LABELS[identifier]} image saved')
            return {'FINISHED'}
        except Exception as exc:
            return _notify_failure(self, exc)

    def _adapt(self, context, identifier, part, payload, stem):
        if not part.reference_png:
            raise ValueError('Generate a Part Reference first')
        obj = component_template(context, identifier)
        if obj is None:
            raise ValueError(f'Choose a source mesh for {COMPONENT_LABELS[identifier]}')
        reference = encode_png(bpy.path.abspath(part.reference_png))
        with tempfile.TemporaryDirectory(prefix='prepare_', dir=stem.parent) as directory:
            folder = Path(directory)
            glb = folder / 'source.glb'
            white = export_source(context, obj, glb, clay_filename=folder / 'clay.png')
            payload.update(white_png_base64=encode_png(white), reference_png_base64=reference)
            result = _request_image(context, '/v1/components/target', payload)
            target = folder / 'target.png'
            save_b64_png(result['image_png_base64'], target)
            mesh_path = stem.with_suffix('.glb')
            target_path = stem.with_suffix('.png')
            glb.replace(mesh_path)
            try:
                target.replace(target_path)
            except OSError:
                mesh_path.unlink(missing_ok=True)
                raise
        if part.source_mesh != obj:
            part.source_mesh = obj
        part.source_glb = str(mesh_path)
        part.target_png = str(target_path)


def register():
    bpy.utils.register_class(EASYKIG_OT_component_image)


def unregister():
    bpy.utils.unregister_class(EASYKIG_OT_component_image)
