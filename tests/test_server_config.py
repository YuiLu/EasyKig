from types import SimpleNamespace

import pytest

from easykig import server_config


def preferences(**values):
    fields = dict(service_mode='self_hosted', server_transport='direct',
                  server_url='http://127.0.0.1:8001', server_token='self-hosted-token',
                  hosted_server_url='https://hosted.example/v1-prefix', hosted_server_token='hosted-token',
                  ssh_local_port=8002)
    return SimpleNamespace(**{**fields, **values})


def test_modes_use_separate_saved_endpoints_and_tokens():
    prefs = preferences()
    assert server_config.server_credentials(prefs) == ('http://127.0.0.1:8001', 'self-hosted-token')
    prefs.service_mode = 'hosted'
    assert server_config.server_credentials(prefs) == ('https://hosted.example/v1-prefix', 'hosted-token')
    assert not server_config.uses_ssh(prefs)
    prefs.server_transport = 'ssh'
    assert not server_config.uses_ssh(prefs)
    prefs.service_mode = 'self_hosted'
    assert server_config.uses_ssh(prefs)
    assert server_config.server_credentials(prefs) == ('http://127.0.0.1:8002', 'self-hosted-token')
    assert prefs.server_url == 'http://127.0.0.1:8001'


def test_empty_hosted_address_has_configuration_guidance():
    with pytest.raises(ValueError, match='Set Service URL'):
        server_config.server_credentials(preferences(service_mode='hosted', hosted_server_url=''))


def test_connect_checks_authentication_and_shapeup_readiness(monkeypatch):
    requests = []
    def reply(url, timeout, headers):
        requests.append((url, dict(headers)))
        if url.endswith('/v1/edit3d/health'):
            return {'ready': True}
        return {'name': 'easykig-gateway', 'status': 'ok', 'authenticated_health': True,
                'mesh_editor_backend': 'shapeup', 'mesh_editor_enabled': True}

    monkeypatch.setattr(server_config, 'http_json', reply)
    assert server_config.check_server('https://hosted.example', 'hosted-token', 5) == 'Connected - ShapeUp ready'
    assert [url for url, _ in requests] == ['https://hosted.example/health',
        'https://hosted.example/v1/health', 'https://hosted.example/v1/edit3d/health']
    assert 'Authorization' not in requests[0][1]
    assert all(headers['Authorization'] == 'Bearer hosted-token' for _, headers in requests[1:])


def test_connect_supports_old_gateways_and_tokenless_ssh(monkeypatch):
    requests = []
    def reply(url, timeout, headers):
        requests.append((url, dict(headers)))
        return {'name': 'easykig-gateway', 'status': 'ok', 'mesh_editor_enabled': True}

    monkeypatch.setattr(server_config, 'http_json', reply)
    assert server_config.check_server('http://127.0.0.1:8001', '', 5) == 'Connected - 3D editing configured'
    assert len(requests) == 1
    assert 'Authorization' not in requests[0][1]


@pytest.mark.parametrize('reply', [{'status': 'ok'}, {'name': 'easykig-gateway', 'status': 'failed'}, []])
def test_connect_rejects_unrelated_or_unhealthy_endpoints(monkeypatch, reply):
    monkeypatch.setattr(server_config, 'http_json', lambda *args: reply)
    with pytest.raises(ValueError, match='EasyKig gateway health'):
        server_config.check_server('https://hosted.example', '', 5)


def test_connect_propagates_authentication_failure(monkeypatch):
    def reply(url, timeout, headers):
        if url.endswith('/v1/health'):
            raise RuntimeError('HTTP 403: Invalid bearer token')
        return {'name': 'easykig-gateway', 'status': 'ok', 'authenticated_health': True}

    monkeypatch.setattr(server_config, 'http_json', reply)
    with pytest.raises(RuntimeError, match='Invalid bearer token'):
        server_config.check_server('https://hosted.example', 'invalid-token', 5)
