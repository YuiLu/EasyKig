"""Unified asynchronous connection actions for the selected service."""
import atexit
import queue
import threading
import time

import bpy

from .ssh_tunnel import SshTunnel
from .server_config import check_server, server_credentials, uses_ssh

_tunnel = SshTunnel()
_events = queue.Queue()
_cancel = threading.Event()
_initialized = False


def initialize_preferences():
    global _initialized
    prefs = bpy.context.preferences.addons[__package__].preferences
    if not _initialized:
        disconnect(prefs)
        _initialized = True
    if not prefs.is_property_set('server_transport'):
        prefs.server_transport = 'ssh' if prefs.ssh_auto_connect else 'direct'


def disconnect(preferences=None):
    _cancel.set()
    _tunnel.stop()
    if preferences is None:
        entry = bpy.context.preferences.addons.get(__package__)
        preferences = entry.preferences if entry else None
    if preferences is not None:
        preferences.connection_state = 'disconnected'
        preferences.connection_message = 'Disconnected'


def _check_connection(cancel, url, token, timeout, ssh):
    try:
        if ssh:
            deadline = time.monotonic() + 15
            while not _tunnel.status.startswith('Connected'):
                if cancel.wait(.1):
                    return
                if _tunnel.status != 'Connecting':
                    raise RuntimeError(_tunnel.status)
                if time.monotonic() > deadline:
                    raise RuntimeError('SSH connection timed out')
        if not cancel.is_set():
            message = check_server(url, token, timeout)
            _events.put((cancel, 'connected', message))
    except Exception as exc:
        _events.put((cancel, 'error', str(exc)))


def start_from_preferences():
    global _cancel
    initialize_preferences()
    prefs = bpy.context.preferences.addons[__package__].preferences
    disconnect(prefs)
    _cancel = threading.Event()
    try:
        if not bpy.app.online_access:
            raise ValueError('Enable Allow Online Access in Blender Preferences')
        url, token = server_credentials(prefs)
        ssh = uses_ssh(prefs)
        if ssh:
            identity = bpy.path.abspath(prefs.ssh_identity) if prefs.ssh_identity else ''
            _tunnel.start(host=prefs.ssh_host.strip(), port=prefs.ssh_port,
                          user=prefs.ssh_user.strip(), identity=identity,
                          local_port=prefs.ssh_local_port, remote_host=prefs.ssh_remote_host.strip(),
                          remote_port=prefs.ssh_remote_port)
        prefs.connection_state = 'connecting'
        prefs.connection_message = 'Opening SSH tunnel...' if ssh else 'Checking server...'
        if not bpy.app.timers.is_registered(_refresh_status):
            bpy.app.timers.register(_refresh_status, first_interval=.1, persistent=True)
        threading.Thread(target=_check_connection,
                         args=(_cancel, url, token, min(prefs.timeout_seconds, 15), ssh), daemon=True).start()
    except (OSError, ValueError, RuntimeError) as exc:
        disconnect(prefs)
        prefs.connection_state = 'error'
        prefs.connection_message = str(exc)
        raise


def _refresh_status():
    entry = bpy.context.preferences.addons.get(__package__)
    if entry is None:
        return None
    prefs = entry.preferences
    changed = False
    while True:
        try:
            cancel, state, message = _events.get_nowait()
        except queue.Empty:
            break
        if cancel is _cancel and not cancel.is_set():
            if state == 'error':
                _tunnel.stop()
            prefs.connection_state = state
            prefs.connection_message = message
            changed = True
    if prefs.connection_state == 'connected' and uses_ssh(prefs) and _tunnel.status.startswith('SSH exited:'):
        prefs.connection_state = 'error'
        prefs.connection_message = _tunnel.status
        changed = True
    if changed:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'PREFERENCES':
                    area.tag_redraw()
    return .25


class EASYKIG_OT_connect_server(bpy.types.Operator):
    bl_idname = 'easykig.connect_server'
    bl_label = 'Connect Server'
    bl_description = 'Connect the selected service, opening SSH if configured, and check gateway authentication and 3D readiness'

    def execute(self, context):
        try:
            start_from_preferences()
        except (OSError, ValueError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class EASYKIG_OT_disconnect_server(bpy.types.Operator):
    bl_idname = 'easykig.disconnect_server'
    bl_label = 'Disconnect Server'

    def execute(self, context):
        disconnect()
        return {'FINISHED'}


class EASYKIG_OT_ssh_connect(bpy.types.Operator):
    bl_idname = 'easykig.ssh_connect'
    bl_label = 'Connect SSH Tunnel'

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        prefs.service_mode = 'self_hosted'
        prefs.server_transport = 'ssh'
        return bpy.ops.easykig.connect_server()


class EASYKIG_OT_ssh_disconnect(bpy.types.Operator):
    bl_idname = 'easykig.ssh_disconnect'
    bl_label = 'Disconnect SSH Tunnel'

    def execute(self, context):
        return bpy.ops.easykig.disconnect_server()


_CLASSES = (EASYKIG_OT_connect_server, EASYKIG_OT_disconnect_server,
            EASYKIG_OT_ssh_connect, EASYKIG_OT_ssh_disconnect)


def register():
    global _initialized
    _initialized = False
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.app.timers.register(initialize_preferences, first_interval=.1)
    atexit.register(_tunnel.stop)


def unregister():
    if bpy.app.timers.is_registered(_refresh_status):
        bpy.app.timers.unregister(_refresh_status)
    if bpy.app.timers.is_registered(initialize_preferences):
        bpy.app.timers.unregister(initialize_preferences)
    disconnect()
    atexit.unregister(_tunnel.stop)
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
