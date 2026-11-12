import base64
import io

import httpx
import numpy as np
from PIL import Image
import pytest
import trimesh
from fastapi.testclient import TestClient

from server.app import app
from server import shapeup

JOB = 'a' * 32
AUTH = {'Authorization': 'Bearer gateway-secret'}


@pytest.fixture
def bridge(monkeypatch, tmp_path):
    monkeypatch.setenv('EASYKIG_SERVER_TOKEN', 'gateway-secret')
    monkeypatch.setenv('EASYKIG_EDIT3D_BACKEND', 'shapeup')
    monkeypatch.setenv('EASYKIG_EDIT3D_UPSTREAM_URL', 'http://127.0.0.1:9000')
    monkeypatch.setenv('EASYKIG_EDIT3D_JOB_DIR', str(tmp_path / 'jobs'))
    monkeypatch.delenv('EASYKIG_EDIT3D_UPSTREAM_TOKEN', raising=False)
    token = tmp_path / 'token'
    token.write_text('private-shapeup-token')
    monkeypatch.setenv('EASYKIG_EDIT3D_UPSTREAM_TOKEN_FILE', str(token))
    mesh = trimesh.creation.box(extents=(.26, .18, .30))
    mesh.apply_translation([1, 2, 3])
    raw = mesh.export(file_type='glb')
    normalized = mesh.copy()
    normalized.vertices = (mesh.vertices - mesh.bounds.mean(axis=0)) / (.30 / 2)
    result = normalized.export(file_type='glb')
    image = io.BytesIO()
    Image.new('RGB', (8, 8), 'white').save(image, format='PNG')
    payload = {'mesh_glb_base64': base64.b64encode(raw).decode(),
               'edit_png_base64': base64.b64encode(image.getvalue()).decode(),
               'seed': 123, 'steps': 12, 'watertight_resolution': 256}
    return tmp_path, mesh, raw, result, payload


def mock_upstream(monkeypatch, handler):
    client_type = httpx.AsyncClient
    monkeypatch.setattr(shapeup.httpx, 'AsyncClient',
        lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs))


def test_shapeup_job_restores_source_coordinates_and_survives_new_client(bridge, monkeypatch):
    temp, source, raw, result, payload = bridge
    requests = []

    def upstream(request):
        assert request.headers['Authorization'] == 'Bearer private-shapeup-token'
        requests.append((request.method, request.url.path))
        if request.url.path == '/readyz':
            return httpx.Response(200, json={'ready': True})
        if request.method == 'POST':
            assert request.url.path == '/jobs'
            assert raw in request.content
            assert b'name="image"; filename="edit.png"' in request.content
            assert b'123' in request.content and b'256' in request.content
            assert b'gateway-secret' not in request.content
            return httpx.Response(202, json={'id': JOB, 'status': 'queued'})
        if request.url.path.endswith('/result'):
            return httpx.Response(200, content=result)
        return httpx.Response(200, json={'id': JOB, 'status': 'succeeded'})

    mock_upstream(monkeypatch, upstream)
    with TestClient(app) as client:
        info = client.get('/health').json()
        assert info['mesh_editor_async'] and info['mesh_editor_requires_image']
        assert client.get('/v1/edit3d/health', headers=AUTH).json()['ready']
        response = client.post('/v1/edit3d/jobs', headers=AUTH, json=payload)
        assert response.status_code == 202, response.text
        assert response.json()['id'] == JOB
    # Status and inverse transform are not kept in an in-memory gateway queue.
    assert (temp / 'jobs' / (JOB + '.json')).is_file()
    with TestClient(app) as client:
        assert client.get('/v1/edit3d/jobs/' + JOB, headers=AUTH).json()['status'] == 'succeeded'
        response = client.get('/v1/edit3d/jobs/' + JOB + '/result', headers=AUTH)
        assert response.status_code == 200, response.text
        restored = trimesh.load(io.BytesIO(response.content), file_type='glb', force='scene')
        np.testing.assert_allclose(restored.bounds, source.bounds, atol=1e-6)
    assert requests.count(('POST', '/jobs')) == 1


def test_shapeup_validates_input_before_submitting(bridge, monkeypatch):
    _, _, _, _, payload = bridge
    mock_upstream(monkeypatch, lambda _: pytest.fail('Must not submit invalid input'))
    with TestClient(app) as client:
        assert client.post('/v1/edit3d/jobs', json=payload).status_code == 401
        no_image = {k: v for k, v in payload.items() if k != 'edit_png_base64'}
        assert client.post('/v1/edit3d/jobs', headers=AUTH, json=no_image).status_code == 422
        broken = {**payload, 'mesh_glb_base64': base64.b64encode(b'glTFbad').decode()}
        assert client.post('/v1/edit3d/jobs', headers=AUTH, json=broken).status_code == 422
        assert client.get('/v1/edit3d/jobs/' + 'b' * 32, headers=AUTH).status_code == 404
        assert client.get('/v1/edit3d/jobs/not-a-job', headers=AUTH).status_code == 422
        assert client.post('/v1/edit3d', headers=AUTH, json=payload).status_code == 409


@pytest.mark.parametrize('upstream_status,expected', [(401, 502), (429, 429), (503, 503)])
def test_shapeup_reports_credentials_queue_and_gpu_errors(bridge, monkeypatch, upstream_status, expected):
    mock_upstream(monkeypatch, lambda _: httpx.Response(upstream_status, json={'detail': 'upstream'}))
    with TestClient(app) as client:
        response = client.get('/v1/edit3d/health', headers=AUTH)
        assert response.status_code == expected
        assert 'private-shapeup-token' not in response.text


def test_failed_job_and_unfinished_result(bridge, monkeypatch):
    _, _, _, _, payload = bridge

    def upstream(request):
        if request.method == 'POST':
            return httpx.Response(202, json={'id': JOB, 'status': 'queued'})
        return httpx.Response(200, json={'id': JOB, 'status': 'failed', 'error': 'CUDA out of memory'})

    mock_upstream(monkeypatch, upstream)
    with TestClient(app) as client:
        assert client.post('/v1/edit3d/jobs', headers=AUTH, json=payload).status_code == 202
        job = client.get('/v1/edit3d/jobs/' + JOB, headers=AUTH).json()
        assert job['status'] == 'failed' and 'memory' in job['error']
        assert client.get('/v1/edit3d/jobs/' + JOB + '/result', headers=AUTH).status_code == 409


def test_generic_contract_keeps_legacy_payload(bridge, monkeypatch):
    _, _, raw, _, payload = bridge
    monkeypatch.setenv('EASYKIG_EDIT3D_BACKEND', 'generic')
    monkeypatch.setenv('EASYKIG_EDIT3D_UPSTREAM_URL', 'https://editor.example/edit')

    def upstream(request):
        import json
        data = json.loads(request.content)
        assert set(data) == {'prompt', 'mesh_glb_base64'}
        return httpx.Response(200, json={'mesh_glb_base64': base64.b64encode(raw).decode()})

    mock_upstream(monkeypatch, upstream)
    with TestClient(app) as client:
        response = client.post('/v1/edit3d', headers=AUTH,
            json={'prompt': 'eyes larger', 'mesh_glb_base64': payload['mesh_glb_base64'],
                  'edit_png_base64': payload['edit_png_base64']})
        assert response.status_code == 200
        assert response.json()['mode'] == 'upstream'
