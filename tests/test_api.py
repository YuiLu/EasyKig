import base64
import os
from fastapi.testclient import TestClient
from server.app import app

PNG_HEADER=b'\x89PNG\r\n\x1a\n'
client=TestClient(app)


def test_health():
    res=client.get('/health')
    assert res.status_code==200
    assert res.json()['status']=='ok'


def test_authenticated_health_checks_gateway_token(monkeypatch):
    monkeypatch.setenv('EASYKIG_AUTH_MODE', 'token')
    monkeypatch.setenv('EASYKIG_SERVER_TOKEN', 'connection-test-token')
    assert client.get('/health').json()['authenticated_health']
    assert client.get('/v1/health').status_code == 401
    assert client.get('/v1/health', headers={'Authorization': 'Bearer wrong'}).status_code == 403
    result = client.get('/v1/health', headers={'Authorization': 'Bearer connection-test-token'})
    assert result.status_code == 200
    assert result.json()['name'] == 'easykig-gateway'


def test_auth_disabled_without_token(monkeypatch):
    monkeypatch.delenv('EASYKIG_SERVER_TOKEN',raising=False)
    monkeypatch.delenv('EASYKIG_ALLOW_UNAUTHENTICATED',raising=False)
    response=client.get('/v1/health')
    assert response.status_code==503


def test_ssh_auth_accepts_loopback_without_gateway_token(monkeypatch):
    monkeypatch.setenv('EASYKIG_AUTH_MODE', 'ssh')
    # An existing token can remain configured when switching to SSH mode.
    monkeypatch.setenv('EASYKIG_SERVER_TOKEN', 'old-token')
    for host in ('127.0.0.1', '::1'):
        with TestClient(app, client=(host, 30000)) as local:
            response = local.get('/v1/health')
            assert response.status_code == 200
            assert local.get('/health').json()['auth_mode'] == 'ssh'


def test_ssh_auth_rejects_nonlocal_peers_and_forwarded_headers(monkeypatch):
    monkeypatch.setenv('EASYKIG_AUTH_MODE', 'ssh')
    with TestClient(app, client=('192.0.2.10', 30000)) as remote:
        response = remote.get('/v1/health',
                               headers={'X-Forwarded-For': '127.0.0.1'})
        assert response.status_code == 403


def test_invalid_auth_mode_is_reported(monkeypatch):
    monkeypatch.setenv('EASYKIG_AUTH_MODE', 'unknown')
    assert client.get('/v1/health').status_code == 503



def test_generation_routes_are_removed():
    for path in ('/v1/preview/finish', '/v1/reference/transform', '/v1/components/reference'):
        assert client.post(path, json={}).status_code == 404
