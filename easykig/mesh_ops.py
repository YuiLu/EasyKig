"""Geometry and Shape Key helpers."""
import math
import bpy

FACE_HINTS = ("face", "顔", "顔面", "脸", "面", "head", "頭", "头", "skin")
NEGATIVE_HINTS = ("hair", "髪", "发", "body", "身体", "服", "skirt", "cloth", "eye", "瞳", "lash", "bone", "arm", "足")


def guess_face_score(obj):
    if obj.type != 'MESH':
        return -1000
    tokens = [obj.name.lower()]
    tokens.extend((slot.material.name.lower() for slot in obj.material_slots if slot.material))
    score = 0
    for token in tokens:
        score += sum(5 for w in FACE_HINTS if w in token)
        score -= sum(4 for w in NEGATIVE_HINTS if w in token)
    score += 1 if obj.data.shape_keys is not None else 0
    return score


def rank_face_objects(objects):
    return sorted((o for o in objects if o.type == 'MESH'), key=guess_face_score, reverse=True)


def get_shape_key_values(obj):
    if obj is None or obj.type != 'MESH' or obj.data.shape_keys is None:
        return {}
    return {k.name: float(k.value) for k in obj.data.shape_keys.key_blocks[1:]}


def get_shape_key_ranges(obj):
    if obj is None or obj.type != 'MESH' or obj.data.shape_keys is None:
        return {}
    return {k.name: [float(k.slider_min), float(k.slider_max)] for k in obj.data.shape_keys.key_blocks[1:]}


def set_shape_key_values(obj, values):
    if obj is None or obj.type != 'MESH' or obj.data.shape_keys is None:
        raise ValueError("Select a Mesh with Shape Keys")
    keys = obj.data.shape_keys.key_blocks
    count = 0
    for name, value in values.items():
        if name == keys[0].name or name not in keys:
            continue
        key = keys[name]
        key.value = max(float(key.slider_min), min(float(key.slider_max), float(value)))
        count += 1
    return count


def evaluated_copy(context, obj, name="Kig Working Face"):
    """Bake active morph / armature into a new static working mesh; preserves source object."""
    depsgraph = context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=depsgraph)
    copy_obj = bpy.data.objects.new(name, mesh)
    context.collection.objects.link(copy_obj)
    copy_obj.matrix_world = obj.matrix_world.copy()
    copy_obj["easykig_role"] = "working_face"
    return copy_obj


def split_copy_by_material(context, obj):
    if obj.type != 'MESH':
        raise ValueError("Expected Mesh")
    # bpy mesh.separate may reject shape keys; always bake into a new mesh first.
    working = evaluated_copy(context, obj, name="Kig Material Working")
    before = set(bpy.data.objects)
    bpy.ops.object.select_all(action='DESELECT')
    working.select_set(True)
    context.view_layer.objects.active = working
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.separate(type='MATERIAL')
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')
    outputs = list((set(bpy.data.objects) - before) | {working})
    for o in outputs:
        if o.type == 'MESH':
            o["easykig_role"] = "material_part"
    return outputs


def ensure_mm_scene(scene):
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.length_unit = 'MILLIMETERS'


def make_demo_template(context):
    """Build a UV ellipsoid with subtle anime face bas-relief, in mm scene units.

    Closed *demonstration* geometry, not a validated wearable / printable mask.
    """
    ensure_mm_scene(context.scene)
    n_lon, n_lat = 64, 40
    vertices = []
    faces = []
    w, d, h = 218.0, 195.0, 255.0
    mm_to_bu = .001 / context.scene.unit_settings.scale_length

    def gauss(x, z, cx, cz, sx, sz):
        return math.exp(-((x-cx)/sx)**2 - ((z-cz)/sz)**2)

    # use almost-polar caps to avoid degenerate faces
    for lat in range(n_lat+1):
        phi = (lat + 0.0001) * math.pi / (n_lat + 0.0002)
        for lon in range(n_lon):
            theta = 2 * math.pi * lon / n_lon
            x = (w/2) * math.sin(phi) * math.sin(theta)
            y = -(d/2) * math.sin(phi) * math.cos(theta)
            z = (h/2) * math.cos(phi)
            front = max(0.0, math.cos(theta))**4
            # recess eye regions; emphasize cheeks and stylized nose
            eye = sum(gauss(x, z, c, 28, 25, 18) for c in (-49,49))
            cheek = sum(gauss(x,z,c,-13,35,30) for c in (-53,53))
            nose = gauss(x,z,0,-8,15,27)
            mouth = gauss(x,z,0,-52,23,7)
            y += front * (6 * eye - 5 * cheek - 7 * nose - 1.5 * mouth)
            vertices.append((x,y,z))
    for lat in range(n_lat):
        for lon in range(n_lon):
            a=lat*n_lon+lon
            b=lat*n_lon+(lon+1)%n_lon
            c=(lat+1)*n_lon+(lon+1)%n_lon
            d0=(lat+1)*n_lon+lon
            faces.append((a,b,c,d0))
    # near-zero circular polar loops capped with ngon
    faces.append(tuple(reversed(tuple(range(n_lon)))))
    faces.append(tuple(n_lat*n_lon + j for j in range(n_lon)))
    mesh=bpy.data.meshes.new("Kig Demo Template Mesh")
    mesh.from_pydata([tuple(axis * mm_to_bu for axis in vertex) for vertex in vertices], [], faces)
    mesh.update()
    obj=bpy.data.objects.new("Kig Demo Template", mesh)
    context.collection.objects.link(obj)
    context.view_layer.objects.active=obj
    obj.select_set(True)
    for p in mesh.polygons:
        p.use_smooth = True
    mat=bpy.data.materials.new("White Resin (Preview)")
    mat.diffuse_color=(.87,.85,.82,1)
    mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get('Principled BSDF')
    if bsdf:
        bsdf.inputs['Base Color'].default_value=(.87,.85,.82,1)
        bsdf.inputs['Roughness'].default_value=.56
    mesh.materials.append(mat)
    obj.shape_key_add(name="Basis", from_mix=False)
    base = [tuple(v) for v in vertices]

    def deform(name, func):
        key = obj.shape_key_add(name=name, from_mix=False)
        for i, (x,y,z) in enumerate(base):
            dx,dy,dz=func(x,y,z)
            key.data[i].co=((x+dx)*mm_to_bu, (y+dy)*mm_to_bu, (z+dz)*mm_to_bu)
        key.value=0.0
        key.slider_min=0.0
        key.slider_max=1.0

    front=lambda y: max(0.0,min(1.0,(-y-18)/90))
    deform('Face Width', lambda x,y,z: (x*.10,0,0))
    deform('Cheek Fullness', lambda x,y,z: (0,-7 * front(y) * (gauss(x,z,55,-16,35,34)+gauss(x,z,-55,-16,35,34)),0))
    deform('Chin Length',lambda x,y,z:(0,0,-12*max(0.0,(-z-38)/90)))
    deform('Forehead Height',lambda x,y,z:(0,0,9*max(0.0,(z-42)/90)))
    deform('Eye Size',lambda x,y,z:(0,5*front(y)*sum(gauss(x,z,c,28,29,23) for c in (-49,49)),0))
    deform('Eye Spacing',lambda x,y,z:(0,4*front(y)*sum((gauss(x,z,c*1.13,28,21,18)-gauss(x,z,c,28,21,18)) for c in (-49,49)),0))
    deform('Nose Projection',lambda x,y,z:(0,-6*front(y)*gauss(x,z,0,-8,18,25),0))
    deform('Mouth Curve',lambda x,y,z:(0,-2.5*front(y)*gauss(x,z,0,-51,28,11),0))
    obj["easykig_role"] = "demo_template"
    obj["easykig_demo_only"] = True
    return obj
