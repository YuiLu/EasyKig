import base64
import os
from fastapi.testclient import TestClient
from server.app import app
from server.prompts import finishing_prompt
from server.shape_rules import propose_edits

PNG_HEADER=b'\x89PNG\r\n\x1a\n'
client=TestClient(app)


def test_health():
    res=client.get('/health')
    assert res.status_code==200
    assert res.json()['status']=='ok'


def test_auth_disabled_without_token(monkeypatch):
    monkeypatch.delenv('EASYKIG_SERVER_TOKEN',raising=False)
    monkeypatch.delenv('EASYKIG_ALLOW_UNAUTHENTICATED',raising=False)
    response=client.post('/v1/edit/parameters',json={'prompt':'眼睛大一点','shape_keys':{'Eye Size':0.2}})
    assert response.status_code==503


def test_parameter_editing(monkeypatch):
    monkeypatch.setenv('EASYKIG_SERVER_TOKEN','demo-test-secret')
    payload={'prompt':'眼睛大一点，脸颊更圆一些',
             'shape_keys':{'Eye Size':0.2,'Cheek Fullness':0.2,'Nose Projection':0.7},
             'ranges':{'Eye Size':[0,1],'Cheek Fullness':[0,1],'Nose Projection':[0,1]}}
    result=client.post('/v1/edit/parameters',headers={'Authorization':'Bearer demo-test-secret'},json=payload)
    assert result.status_code==200
    values=result.json()['shape_keys']
    assert values['Eye Size']>0.2
    assert values['Cheek Fullness']>0.2
    assert values['Nose Projection']==0.7
    assert result.json()['mode']=='rules'


def test_unrecognized_edit_remains_unchanged(monkeypatch):
    monkeypatch.setenv('EASYKIG_SERVER_TOKEN','secret')
    response=client.post('/v1/edit/parameters',headers={'Authorization':'Bearer secret'},
                         json={'prompt':'Make it more like my reference',
                               'shape_keys':{'Eye Size':0.4},'ranges':{'Eye Size':[0,1]}})
    assert response.status_code==200
    assert response.json()['shape_keys']['Eye Size']==0.4
    assert response.json()['changes']=={}


def test_image_endpoint_reports_missing_key(monkeypatch):
    monkeypatch.setenv('EASYKIG_SERVER_TOKEN','secret')
    monkeypatch.delenv('OPENAI_IMAGE_API_KEY',raising=False)
    response=client.post('/v1/preview/finish',headers={'Authorization':'Bearer secret'},
                         json={'white_png_base64':base64.b64encode(PNG_HEADER+b'abc').decode(),'prompt':'pink'})
    assert response.status_code==503


def test_edit3d_unconfigured(monkeypatch):
    monkeypatch.setenv('EASYKIG_SERVER_TOKEN','secret')
    monkeypatch.delenv('EASYKIG_EDIT3D_UPSTREAM_URL',raising=False)
    res=client.post('/v1/edit3d',headers={'Authorization':'Bearer secret'},
                    json={'prompt':'eyes larger','mesh_glb_base64':base64.b64encode(b'glTF'+b'0'*20).decode()})
    assert res.status_code==501


def test_prompt_structural_constraint():
    s=finishing_prompt('purple wig and orange eyes')
    assert 'camera' in s.lower()
    assert 'purple wig' in s


def test_reference_preset_forwarded_verbatim(monkeypatch, tmp_path):
    from server import app as gateway

    monkeypatch.setenv('EASYKIG_SERVER_TOKEN', 'secret')
    monkeypatch.setenv('EASYKIG_REFERENCE_PROMPTS_DIR', str(tmp_path))
    preset = '第一行\r\n  第二行 {details}\r\n'
    (tmp_path / 'product.txt').write_bytes(preset.encode('utf-8'))
    source = PNG_HEADER + b'source'
    extra = PNG_HEADER + b'expression'

    async def fake_provider(images, prompt, model):
        assert images == [source, extra]
        assert prompt == preset
        return base64.b64encode(source).decode()

    monkeypatch.setattr(gateway, 'provider_image_edit', fake_provider)
    response = client.post(
        '/v1/reference/transform',
        headers={'Authorization': 'Bearer secret'},
        json={
            'stage': 'product',
            'source_png_base64': base64.b64encode(source).decode(),
            'additional_png_base64': [base64.b64encode(extra).decode()],
            'prompt': 'must not be appended',
        },
    )
    assert response.status_code == 200
    assert response.json()['stage'] == 'product'


def test_configured_reference_preset_missing_file(monkeypatch, tmp_path):
    monkeypatch.setenv('EASYKIG_SERVER_TOKEN', 'secret')
    monkeypatch.setenv('EASYKIG_REFERENCE_PROMPTS_DIR', str(tmp_path))
    response = client.post(
        '/v1/reference/transform',
        headers={'Authorization': 'Bearer secret'},
        json={'stage': 'head', 'source_png_base64': base64.b64encode(PNG_HEADER).decode()},
    )
    assert response.status_code == 503
    assert 'preset' in response.json()['detail']


def test_image_model_is_selected_only_from_gateway_models(monkeypatch):
    from server import app as gateway

    monkeypatch.setenv('EASYKIG_SERVER_TOKEN', 'secret')
    monkeypatch.setenv('OPENAI_IMAGE_MODEL', 'default-image')
    monkeypatch.setenv('EASYKIG_IMAGE_MODELS', 'fast-image, default-image')
    seen = []
    png = base64.b64encode(PNG_HEADER).decode()

    async def fake_provider(images, prompt, model):
        seen.append(model)
        return png

    monkeypatch.setattr(gateway, 'provider_image_edit', fake_provider)
    headers = {'Authorization': 'Bearer secret'}
    assert client.get('/health').json()['image_models'] == ['default-image', 'fast-image']
    url = '/v1/preview/finish'
    payload = {'white_png_base64': png}
    assert client.post(url, headers=headers, json=payload).status_code == 200
    assert client.post(url, headers=headers, json={**payload, 'model': 'fast-image'}).status_code == 200
    assert client.post(url, headers=headers, json={**payload, 'model': 'unknown'}).status_code == 422
    assert seen == ['default-image', 'fast-image']
