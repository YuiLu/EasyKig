"""Isolated white-clay rendering from the evaluated template meshes."""
import tempfile
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


def output_folder(settings):
    path = settings.preview_output_dir
    if not path or (path.startswith('//') and not bpy.data.filepath):
        folder = Path(tempfile.gettempdir()) / 'easykig_outputs'
    else:
        folder = Path(bpy.path.abspath(path))
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def white_render(context, obj, filename='white_front.png'):
    if obj is None or obj.type != 'MESH':
        raise ValueError('Please select a face mesh')
    settings = context.scene.easykig_settings
    output_path = str(output_folder(settings) / filename)
    group = settings.template_collection
    sources = [obj]
    if group:
        sources.extend(
            part for part in group.all_objects
            if part != obj and part.type == 'MESH' and part.name in context.view_layer.objects
        )

    depsgraph = context.evaluated_depsgraph_get()
    scene = bpy.data.scenes.new('EasyKig White Preview')
    created_objects = []
    created_data = []
    try:
        def add_object(name, data, datablocks):
            created_data.append((datablocks, data))
            item = bpy.data.objects.new(name, data)
            created_objects.append(item)
            scene.collection.objects.link(item)
            return item

        white = bpy.data.materials.new('EasyKig Clay')
        created_data.append((bpy.data.materials, white))
        white.use_nodes = True
        shader = white.node_tree.nodes.get('Principled BSDF')
        shader.inputs['Base Color'].default_value = (.86, .84, .82, 1)
        shader.inputs['Roughness'].default_value = .55

        objects = []
        bounds = []
        for source in sources:
            evaluated = source.evaluated_get(depsgraph)
            mesh = bpy.data.meshes.new_from_object(evaluated)
            part = add_object('EasyKig Clay Part', mesh, bpy.data.meshes)
            objects.append(part)
            part.matrix_world = evaluated.matrix_world
            if mesh.vertices:
                bounds.extend(evaluated.matrix_world @ Vector(v) for v in evaluated.bound_box)

        if not bounds:
            raise ValueError('The template has no geometry to render')
        low = Vector(tuple(min(v[axis] for v in bounds) for axis in range(3)))
        high = Vector(tuple(max(v[axis] for v in bounds) for axis in range(3)))
        mid = (low + high) / 2
        radius = max((v - mid).length for v in bounds)
        if radius <= 0:
            raise ValueError('The template has zero size')
        normalize = Matrix.Scale(1 / radius, 4) @ Matrix.Translation(-mid)

        for part in objects:
            part.matrix_world = normalize @ part.matrix_world
            part.data.materials.clear()
            part.data.materials.append(white)

        camera_data = bpy.data.cameras.new('EasyKig Preview Camera')
        camera = add_object('EasyKig Preview Camera', camera_data, bpy.data.cameras)
        camera.location = (0, -4, .22)
        camera.rotation_euler = (-camera.location).to_track_quat('-Z', 'Y').to_euler()
        camera_data.type = 'ORTHO'
        camera_data.ortho_scale = 2.3
        scene.camera = camera

        for name, position, power, size in (
            ('Key', (-2.8, -2.8, 2.8), 420, 2.6),
            ('Fill', (2.4, -2, 1), 90, 3.2),
        ):
            data = bpy.data.lights.new(name, 'AREA')
            light = add_object(name, data, bpy.data.lights)
            data.energy = power
            data.shape = 'DISK'
            data.size = size
            light.location = position
            light.rotation_euler = (-light.location).to_track_quat('-Z', 'Y').to_euler()

        scene.render.engine = 'CYCLES'
        scene.cycles.device = 'CPU'
        scene.cycles.samples = 12
        scene.cycles.use_denoising = True
        scene.render.resolution_x = 1024
        scene.render.resolution_y = 1024
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = 'PNG'
        scene.render.filepath = output_path
        if 'FINISHED' not in bpy.ops.render.render(write_still=True, scene=scene.name):
            raise RuntimeError('White clay rendering was cancelled')
    finally:
        for item in reversed(created_objects):
            bpy.data.objects.remove(item, do_unlink=True)
        bpy.data.scenes.remove(scene)
        for datablocks, data in reversed(created_data):
            if data.users == 0:
                datablocks.remove(data)

    settings.last_white_png = output_path
    return output_path
