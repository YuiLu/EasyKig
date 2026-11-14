"""Selected server credentials and connection checks, independent of Blender."""
from .http_client import http_json, normalize_url


def uses_ssh(preferences):
    return preferences.service_mode == 'self_hosted' and preferences.server_transport == 'ssh'


def server_credentials(preferences):
    if preferences.service_mode == 'hosted':
        if not preferences.hosted_server_url.strip():
            raise ValueError('Set Service URL for the hosted service in EasyKig preferences')
        return normalize_url(preferences.hosted_server_url), preferences.hosted_server_token
    if uses_ssh(preferences):
        return f'http://127.0.0.1:{preferences.ssh_local_port}', preferences.server_token
    return normalize_url(preferences.server_url), preferences.server_token


def check_server(url, token, timeout):
    headers = {'Accept': 'application/json'}
    info = http_json(url + '/health', timeout, headers)
    if not isinstance(info, dict) or info.get('status') != 'ok' or info.get('name') != 'easykig-gateway':
        raise ValueError('The address did not return an EasyKig gateway health response')
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if info.get('authenticated_health'):
        http_json(url + '/v1/health', timeout, headers)
    if info.get('mesh_editor_backend') == 'shapeup' and info.get('mesh_editor_enabled'):
        ready = http_json(url + '/v1/edit3d/health', timeout, headers)
        if not ready.get('ready'):
            raise ValueError('ShapeUp is not ready')
        return 'Connected - ShapeUp ready'
    if info.get('mesh_editor_enabled'):
        return 'Connected - 3D editing configured'
    return 'Connected - 3D editing is not configured on this gateway'
