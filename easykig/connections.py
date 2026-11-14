"""Blender preference actions for the SSH forward owned by this process."""
import atexit

import bpy

from .ssh_tunnel import SshTunnel

_tunnel = SshTunnel()


def start_from_preferences():
    prefs = bpy.context.preferences.addons[__package__].preferences
    identity = bpy.path.abspath(prefs.ssh_identity) if prefs.ssh_identity else ''
    try:
        _tunnel.start(host=prefs.ssh_host.strip(), port=prefs.ssh_port,
                      user=prefs.ssh_user.strip(), identity=identity,
                      local_port=prefs.ssh_local_port, remote_host=prefs.ssh_remote_host.strip(),
                      remote_port=prefs.ssh_remote_port)
        prefs.server_url = f'http://127.0.0.1:{prefs.ssh_local_port}'
    except (OSError, ValueError, RuntimeError) as exc:
        _tunnel.status = str(exc)
        raise
    finally:
        if not bpy.app.timers.is_registered(_refresh_status):
            bpy.app.timers.register(_refresh_status, first_interval=.5, persistent=True)


def _refresh_status():
    entry = bpy.context.preferences.addons.get(__package__)
    if entry is None:
        return None
    prefs = entry.preferences
    if prefs.ssh_status != _tunnel.status:
        prefs.ssh_status = _tunnel.status
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'PREFERENCES':
                    area.tag_redraw()
    return 1.0


class EASYKIG_OT_ssh_connect(bpy.types.Operator):
    bl_idname = 'easykig.ssh_connect'
    bl_label = 'Connect SSH Tunnel'

    def execute(self, context):
        try:
            start_from_preferences()
        except (OSError, ValueError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, 'Starting SSH tunnel; use Test EasyKig Server after it connects')
        return {'FINISHED'}


class EASYKIG_OT_ssh_disconnect(bpy.types.Operator):
    bl_idname = 'easykig.ssh_disconnect'
    bl_label = 'Disconnect SSH Tunnel'

    def execute(self, context):
        _tunnel.stop()
        context.preferences.addons[__package__].preferences.ssh_status = _tunnel.status
        return {'FINISHED'}


_CLASSES = (EASYKIG_OT_ssh_connect, EASYKIG_OT_ssh_disconnect)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    atexit.register(_tunnel.stop)


def unregister():
    if bpy.app.timers.is_registered(_refresh_status):
        bpy.app.timers.unregister(_refresh_status)
    _tunnel.stop()
    atexit.unregister(_tunnel.stop)
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
