import textwrap

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from .image_preview import extra_preview_items, reference_preview_items, result_preview_items


MAX_REFERENCE_IMAGES = 4
PROMPT_FIELDS = 64


def reset_reference_results(settings, _context):
    settings.last_head_png = ''
    settings.last_design_png = ''
    settings.last_product_png = ''


def clear_image_catalog(preferences, _context):
    preferences.image_catalog.clear()


def get_image_prompt(settings):
    if settings.image_prompt_text is not None:
        return settings.image_prompt_text.as_string()
    return settings.finishing_prompt


def set_image_prompt(settings, value):
    if settings.image_prompt_text is not None:
        settings.image_prompt_text.clear()
        settings.image_prompt_text.write(value)
    else:
        settings.finishing_prompt = value


def image_prompt_rows(settings):
    context = bpy.context
    region = context.region
    width = 36
    if region and region.type == 'UI':
        width = max(16, int((region.width / context.preferences.system.ui_scale - 56) / 7))
    wrapper = textwrap.TextWrapper(
        width=width, expand_tabs=False, replace_whitespace=False, drop_whitespace=False,
    )
    lines = get_image_prompt(settings).replace('\r\n', '\n').split('\n')
    rows = []
    for index, line in enumerate(lines):
        parts = wrapper.wrap(line) or ['']
        if index < len(lines) - 1:
            parts[-1] += '\n'
        rows.extend(parts)
    return rows


def _prompt_row_property(index):
    def get(settings):
        rows = image_prompt_rows(settings)
        return rows[index].removesuffix('\n') if index < len(rows) else ''

    def set_value(settings, value):
        rows = image_prompt_rows(settings)
        if index < len(rows):
            original = rows[index]
            ending = '\n' if original.endswith('\n') else ''
            if not ending and index + 1 < len(rows) and value and not value[-1].isspace():
                ending = original[len(original.rstrip(' \t')):]
            if index and not rows[index - 1].endswith('\n') and value and not value[0].isspace():
                value = original[:len(original) - len(original.lstrip(' \t'))] + value
            rows[index] = value + ending
            set_image_prompt(settings, ''.join(rows))
        elif value:
            set_image_prompt(settings, ''.join(rows) + '\n' * (index - len(rows) + 1) + value)

    return StringProperty(name='Prompt Line', get=get, set=set_value, maxlen=1500)


def reference_paths(settings):
    return [path for path in (settings.reference_image, *(item.path for item in settings.extra_references)) if path]


class EASYKIG_ImageModel(bpy.types.PropertyGroup):
    pass


class EASYKIG_ReferenceImage(bpy.types.PropertyGroup):
    path: StringProperty(subtype='FILE_PATH')
    thumbnail: EnumProperty(items=extra_preview_items, options={'SKIP_SAVE'})


class EASYKIG_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    server_url: StringProperty(
        name="3D Editing Server URL",
        description="Remote server root, e.g. https://your-domain.example. Never include credentials in URL",
        default="http://127.0.0.1:8001",
        update=clear_image_catalog,
    )
    server_token: StringProperty(
        name="Server Token", subtype="PASSWORD", default="", update=clear_image_catalog,
        description='Leave empty when the gateway uses SSH authentication (EASYKIG_AUTH_MODE=ssh)',
    )
    ssh_auto_connect: BoolProperty(
        name='Auto-connect SSH on Development Launch',
        description='dev-blender.ps1 opens a tunnel using these saved preferences',
    )
    ssh_host: StringProperty(name='SSH Host / Config Alias', description='Host name or an alias from ~/.ssh/config')
    ssh_port: IntProperty(name='SSH Port', default=0, min=0, max=65535,
                          description='0 uses the port in SSH config, or the OpenSSH default')
    ssh_user: StringProperty(name='SSH User', description='Leave empty to use SSH config')
    ssh_identity: StringProperty(name='SSH Identity File', subtype='FILE_PATH',
                                 description='Optional private key path. Leave empty to use SSH config or ssh-agent')
    ssh_local_port: IntProperty(name='Local Port', default=8001, min=1, max=65535)
    ssh_remote_host: StringProperty(name='Remote Host', default='127.0.0.1')
    ssh_remote_port: IntProperty(name='Remote Gateway Port', default=8001, min=1, max=65535)
    ssh_status: StringProperty(name='SSH Status', default='Disconnected', options={'SKIP_SAVE'})
    timeout_seconds: FloatProperty(name="Request Timeout (s)", default=360, min=5, max=600)
    mesh_timeout_seconds: FloatProperty(name='3D Job Wait Timeout (s)', default=7200, min=60, max=14400)
    image_provider: EnumProperty(
        name="Image Provider",
        items=[
            ('gateway', 'EasyKig Server', 'Use the image API configured on the EasyKig server', 0),
            ('chatgpt_credits', 'ChatGPT API Credits', 'Use the OpenAI project linked to eligible ChatGPT API credits', 1),
            ('direct', 'OpenAI-compatible Gateway', 'Configure an image API directly in Blender', 2),
        ],
        default='gateway',
        update=clear_image_catalog,
    )
    image_model: StringProperty(
        name="Image Model", maxlen=160,
        description="Model ID allowed by the gateway. Leave blank to use its default",
    )
    subscription_image_model: StringProperty(
        name="Image Model", maxlen=160,
        description="OpenAI image model from the linked project. Leave blank to use its default",
    )
    image_api_base: StringProperty(
        name='Image API Base URL',
        description='OpenAI-compatible API base, for example https://gateway.example/v1',
        update=clear_image_catalog,
    )
    image_api_key: StringProperty(
        name='Image API Key', subtype='PASSWORD', update=clear_image_catalog,
        description='Bearer API key for the configured image gateway',
    )
    direct_image_model: StringProperty(name='Image Model', maxlen=160)
    use_server_prompt_presets: BoolProperty(
        name='Use EasyKig Server Prompt Presets',
        description='Fetch the server’s reference-stage prompt before sending images to the configured image API',
    )
    image_catalog: CollectionProperty(type=EASYKIG_ImageModel, options={'SKIP_SAVE'})
    preview_directory: StringProperty(
        name="Preview Folder Override", subtype="DIR_PATH",
        description="Leave blank to use the project's preview folder",
    )

    def draw(self, context):
        server = self.layout.box()
        server.label(text='EasyKig Server')
        server.prop(self, "server_url")
        server.prop(self, "server_token")
        server.operator('easykig.health', text='Test EasyKig Server', icon='CHECKMARK')
        tunnel = self.layout.box()
        tunnel.label(text='SSH Tunnel')
        tunnel.prop(self, 'ssh_auto_connect')
        tunnel.prop(self, 'ssh_host')
        tunnel.prop(self, 'ssh_port')
        tunnel.prop(self, 'ssh_user')
        tunnel.prop(self, 'ssh_identity')
        tunnel.prop(self, 'ssh_local_port')
        tunnel.prop(self, 'ssh_remote_host')
        tunnel.prop(self, 'ssh_remote_port')
        row = tunnel.row(align=True)
        row.operator('easykig.ssh_connect', text='Connect', icon='LINKED')
        row.operator('easykig.ssh_disconnect', text='Disconnect', icon='UNLINKED')
        tunnel.label(text=self.ssh_status)
        tunnel.label(text='Uses OpenSSH config, keys and ssh-agent.')
        col = self.layout.box()
        col.label(text='Image Generation')
        col.prop(self, "image_provider")
        if self.image_provider == 'direct':
            col.prop(self, "image_api_base")
            col.prop(self, "image_api_key")
            col.prop(self, "use_server_prompt_presets")
        model_field = {
            'gateway': 'image_model',
            'chatgpt_credits': 'subscription_image_model',
            'direct': 'direct_image_model',
        }[self.image_provider]
        if self.image_provider == 'direct' or not self.image_catalog:
            col.prop(self, model_field, text='Model ID')
        if self.image_catalog:
            col.prop_search(self, model_field, self, 'image_catalog', text='Choose Model')
        col.operator('easykig.refresh_image_models', text='Test Image API & Refresh Models', icon='FILE_REFRESH')
        col = self.layout.column(align=True)
        col.prop(self, "timeout_seconds")
        col.prop(self, "mesh_timeout_seconds")
        col.prop(self, "preview_directory")
        col.operator('wm.save_userpref', text='Save Preferences', icon='CHECKMARK')


class EASYKIG_Settings(bpy.types.PropertyGroup):
    face: PointerProperty(name="Face / Template", type=bpy.types.Object)
    template_collection: PointerProperty(
        name="Preview Collection", type=bpy.types.Collection,
        description="Include other meshes from this collection in white previews",
    )
    pmx_meters_per_unit: FloatProperty(
        name="PMX Scale (m / unit)", default=.08, min=.0001, max=10, precision=4,
    )
    height_mm: FloatProperty(name="Target Height (mm)", default=260, min=100, max=600)
    shell_thickness_mm: FloatProperty(name="Shell Thickness (mm)", default=2.0, min=0.5, max=12)
    preview_output_dir: StringProperty(name="Preview Directory", default="//easykig_outputs", subtype="DIR_PATH")
    reference_image: StringProperty(
        name="Reference Image", subtype="FILE_PATH", update=reset_reference_results,
    )
    extra_references: CollectionProperty(type=EASYKIG_ReferenceImage)
    expression_image: StringProperty(
        name="Face Expression", subtype="FILE_PATH",
        description="Optional expression reference for Head, Design and Product",
    )
    character_image: StringProperty(
        name="Character Color Palette", subtype="FILE_PATH",
        description="Optional hair, eye and character colors for Head",
    )
    shell_example_image: StringProperty(
        name="Shell Style Example", subtype="FILE_PATH",
        description="Optional example of shell construction or finish for Design and Product",
    )
    finishing_prompt: StringProperty(
        name="Finish Description", default="soft pink skin, anime eyes, delicate blush, styled wig, premium handcrafted cosplay kigurumi mask",
    )
    image_prompt_text: PointerProperty(name='Image Prompt', type=bpy.types.Text)
    editing_prompt: StringProperty(name="Shape Edit Instruction", default="Rounder cheeks and larger eyes")
    mesh_edit_source: EnumProperty(
        name='Target Image', default='finished',
        items=[('finished', 'Finished Preview', 'Use the finished clay-view edit as the desired shape and appearance'),
               ('design', 'Design Reference', 'Use the generated kigurumi design'),
               ('product', 'Product Reference', 'Use the generated product image'),
               ('head', 'Head Reference', 'Use the generated head reference'),
               ('reference', 'Original Reference', 'Use the first reference image'),
               ('file', 'Image File', 'Choose a target edit image from disk')])
    mesh_edit_image: StringProperty(name='3D Edit Image', subtype='FILE_PATH')
    mesh_edit_seed: IntProperty(name='Seed', default=10, min=0, max=2147483647)
    mesh_edit_steps: IntProperty(name='Geometry Steps', default=30, min=1, max=100)
    mesh_edit_resolution: EnumProperty(name='Watertight Resolution', default='512',
        items=[('128', '128', 'Fastest mesh preparation'), ('256', '256', 'Lower preparation memory'),
               ('512', '512', 'Default ShapeUp quality; higher GPU memory while preparing')])
    mesh_job_id: StringProperty(name='3D Task ID')
    mesh_job_status: StringProperty(name='3D Status', default='idle', options={'SKIP_SAVE'})
    mesh_job_message: StringProperty(name='3D Message', options={'SKIP_SAVE'})
    mesh_job_running: BoolProperty(default=False, options={'SKIP_SAVE'})
    mesh_result_glb: StringProperty(name='Edited GLB', subtype='FILE_PATH')
    last_head_png: StringProperty(name="Head Reference", default="")
    last_design_png: StringProperty(name="Kigurumi Design", default="")
    last_product_png: StringProperty(name="Product Reference", default="")
    last_white_png: StringProperty(name="White Render", default="")
    last_finished_png: StringProperty(name="Finished Preview", default="")
    result_view: EnumProperty(
        name="Preview",
        items=[
            ('head', 'Head', 'Character head reference'),
            ('design', 'Design', 'Kigurumi design reference'),
            ('product', 'Product', 'Product reference'),
            ('white', 'White Clay', 'White clay render'),
            ('finished', 'Finished', 'Finished preview'),
        ],
        default='finished',
    )
    reference_thumbnail: EnumProperty(items=reference_preview_items, options={'SKIP_SAVE'})
    result_thumbnail: EnumProperty(items=result_preview_items, options={'SKIP_SAVE'})


for _index in range(PROMPT_FIELDS):
    EASYKIG_Settings.__annotations__[f'prompt_row_{_index}'] = _prompt_row_property(_index)


_CLASSES = (EASYKIG_ImageModel, EASYKIG_ReferenceImage, EASYKIG_AddonPreferences, EASYKIG_Settings)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.easykig_settings = PointerProperty(type=EASYKIG_Settings)


def unregister():
    del bpy.types.Scene.easykig_settings
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
