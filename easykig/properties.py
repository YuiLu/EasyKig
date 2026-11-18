import textwrap

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from .image_preview import reference_preview_items


def connection_settings_changed(preferences, _context):
    from .connections import disconnect
    disconnect(preferences)


class EASYKIG_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    service_mode: EnumProperty(
        name='Service', default='self_hosted',
        items=[('hosted', 'Hosted Service', 'Connect to a managed EasyKig gateway', 0),
               ('self_hosted', 'Self-hosted Service', 'Connect to your own EasyKig gateway', 1)],
        update=connection_settings_changed,
    )
    hosted_server_url: StringProperty(name='Service URL', update=connection_settings_changed)
    hosted_server_token: StringProperty(name='Access Token', subtype='PASSWORD', update=connection_settings_changed)
    server_transport: EnumProperty(
        name='Connection', default='direct',
        items=[('direct', 'Direct URL', 'Connect to a gateway URL', 0),
               ('ssh', 'SSH Tunnel', 'Forward a remote gateway through OpenSSH', 1)],
        update=connection_settings_changed,
    )
    server_url: StringProperty(
        name="Server URL",
        description="Remote server root, e.g. https://your-domain.example. Never include credentials in URL",
        default="http://127.0.0.1:8001",
        update=connection_settings_changed,
    )
    server_token: StringProperty(
        name="Server Token", subtype="PASSWORD", default="", update=connection_settings_changed,
        description='Leave empty when the gateway uses SSH authentication (EASYKIG_AUTH_MODE=ssh)',
    )
    ssh_auto_connect: BoolProperty(
        name='Auto-connect on Development Launch',
        description='dev-blender.ps1 connects the selected service using these saved preferences',
    )
    ssh_host: StringProperty(name='SSH Host / Config Alias', description='Host name or an alias from ~/.ssh/config',
                             update=connection_settings_changed)
    ssh_port: IntProperty(name='SSH Port', default=0, min=0, max=65535,
                          description='0 uses the port in SSH config, or the OpenSSH default',
                          update=connection_settings_changed)
    ssh_user: StringProperty(name='SSH User', description='Leave empty to use SSH config', update=connection_settings_changed)
    ssh_identity: StringProperty(name='SSH Identity File', subtype='FILE_PATH',
                                 description='Private key file. OpenSSH can use an unencrypted key directly or a key loaded in ssh-agent',
                                 update=connection_settings_changed)
    ssh_local_port: IntProperty(name='Local Port', default=8001, min=1, max=65535, update=connection_settings_changed)
    ssh_remote_host: StringProperty(name='Remote Host', default='127.0.0.1', update=connection_settings_changed)
    ssh_remote_port: IntProperty(name='Remote Gateway Port', default=8001, min=1, max=65535, update=connection_settings_changed)
    ssh_advanced: BoolProperty(name='Advanced Tunnel Settings')
    connection_state: EnumProperty(
        items=[('disconnected', 'Disconnected', ''), ('connecting', 'Connecting', ''),
               ('connected', 'Connected', ''), ('error', 'Connection Error', '')],
        default='disconnected', options={'SKIP_SAVE'},
    )
    connection_message: StringProperty(default='Disconnected', options={'SKIP_SAVE'})
    timeout_seconds: FloatProperty(name="Request Timeout (s)", default=360, min=5, max=600)
    mesh_timeout_seconds: FloatProperty(name='3D Job Wait Timeout (s)', default=7200, min=60, max=14400)
    preview_directory: StringProperty(
        name="Result Folder", subtype="DIR_PATH",
        description="Leave blank to use the project's output folder",
    )

    def draw(self, context):
        server = self.layout.box()
        server.label(text='Server Connection')
        server.row().prop(self, 'service_mode', expand=True)
        fields = server.column()
        fields.use_property_split = True
        fields.use_property_decorate = False
        if self.service_mode == 'hosted':
            fields.prop(self, 'hosted_server_url')
            fields.prop(self, 'hosted_server_token')
        else:
            fields.row(align=True).prop(self, 'server_transport', expand=True)
            if self.server_transport == 'ssh':
                fields.prop(self, 'ssh_host')
                fields.prop(self, 'ssh_port')
                fields.prop(self, 'ssh_user')
                fields.prop(self, 'ssh_identity')
                advanced = fields.row()
                advanced.use_property_split = False
                advanced.prop(self, 'ssh_advanced', emboss=False,
                              icon='TRIA_DOWN' if self.ssh_advanced else 'TRIA_RIGHT')
                if self.ssh_advanced:
                    fields.prop(self, 'ssh_local_port')
                    fields.prop(self, 'ssh_remote_host')
                    fields.prop(self, 'ssh_remote_port')
                    fields.prop(self, 'server_token', text='Server Token (Optional)')
            else:
                fields.prop(self, 'server_url')
                fields.prop(self, 'server_token')
        server.prop(self, 'ssh_auto_connect')
        row = server.row(align=True)
        connect = row.row(align=True)
        connect.enabled = self.connection_state != 'connecting'
        connect.scale_y = 1.2
        connect.operator('easykig.connect_server', text='Connect Server', icon='URL')
        if self.connection_state in {'connecting', 'connected'}:
            row.operator('easykig.disconnect_server', text='', icon='X')
        width = max(32, int(context.region.width / context.preferences.system.ui_scale / 7) - 5) if context.region else 72
        status = server.column(align=True)
        status.alert = self.connection_state == 'error'
        for line in textwrap.wrap(self.connection_message, width=width):
            status.label(text=line)
        col = self.layout.column(align=True)
        col.prop(self, "timeout_seconds")
        col.prop(self, "mesh_timeout_seconds")
        col.prop(self, "preview_directory")
        col.operator('wm.save_userpref', text='Save Preferences', icon='CHECKMARK')


class EASYKIG_Settings(bpy.types.PropertyGroup):
    face: PointerProperty(name='Source Mesh', type=bpy.types.Object, poll=lambda _self, obj: obj.type == 'MESH')
    mesh_edit_image: StringProperty(name='Component Reference', subtype='FILE_PATH')
    editing_prompt: StringProperty(name='Editing Notes', default='', maxlen=1500)
    preview_output_dir: StringProperty(name='Result Directory', default='//easykig_outputs', subtype='DIR_PATH')
    mesh_edit_seed: IntProperty(name='Seed', default=10, min=0, max=2147483647)
    mesh_edit_steps: IntProperty(name='Geometry Steps', default=30, min=1, max=100)
    mesh_edit_resolution: EnumProperty(name='Watertight Resolution', default='512',
        items=[('128', '128', 'Fastest preparation'), ('256', '256', 'Lower memory'),
               ('512', '512', 'Higher detail')])
    mesh_job_id: StringProperty(name='3D Task ID')
    mesh_job_status: StringProperty(default='idle', options={'SKIP_SAVE'})
    mesh_job_message: StringProperty(options={'SKIP_SAVE'})
    mesh_job_running: BoolProperty(default=False, options={'SKIP_SAVE'})
    mesh_result_glb: StringProperty(subtype='FILE_PATH')
    reference_thumbnail: EnumProperty(items=reference_preview_items, options={'SKIP_SAVE'})


_CLASSES = (EASYKIG_AddonPreferences, EASYKIG_Settings)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.easykig_settings = PointerProperty(type=EASYKIG_Settings)


def unregister():
    del bpy.types.Scene.easykig_settings
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
