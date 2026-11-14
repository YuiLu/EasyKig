"""EasyKig remote gateway (FastAPI).

Contracts:
  GET  /health
  POST /v1/edit/parameters
  POST /v1/preview/finish
  POST /v1/edit3d

Preview requires OPENAI_IMAGE_API_KEY. 3D editing uses either a compatible generic
upstream or ShapeUp's image-conditioned job queue; both are opt-in.
"""
import base64
import hmac
import ipaddress
import os
from typing import Annotated, Literal
from urllib.parse import urlparse
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
import httpx

from .prompts import finishing_prompt, reference_prompt
from .shape_rules import propose_edits
from .shapeup import ShapeUp, backend as edit3d_backend

MAX_PNG=8*1024*1024
MAX_GLB=20*1024*1024
PNGSIG=b'\x89PNG\r\n\x1a\n'

app=FastAPI(title='EasyKig Remote Gateway',version='0.1.2',docs_url=None,redoc_url=None)


def setting(name: str, default: str = '') -> str:
    return os.getenv(f'EASYKIG_{name}', os.getenv(f'KIGSHELL_{name}', default))


def require_auth(request: Request, authorization: str|None=Header(default=None)):
    mode = setting('AUTH_MODE', 'token')
    if mode == 'ssh':
        try:
            local = request.client is not None and ipaddress.ip_address(request.client.host).is_loopback
        except ValueError:
            local = False
        if not local:
            raise HTTPException(status_code=403, detail='SSH authentication requires a loopback connection to the gateway')
        return
    if mode != 'token':
        raise HTTPException(status_code=503, detail='EASYKIG_AUTH_MODE must be token or ssh')
    expected=setting('SERVER_TOKEN','')
    if not expected:
        # Retain the explicitly enabled legacy local-development option.
        if setting('ALLOW_UNAUTHENTICATED','0')=='1':
            return
        raise HTTPException(status_code=503,detail='Server token is not configured')
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401,detail='Bearer token required')
    if not hmac.compare_digest(authorization[7:],expected):
        raise HTTPException(status_code=403,detail='Invalid bearer token')


def decode_binary(value: str, signature: bytes, limit: int, name: str):
    # Guard encoded size before decoding, including base64 inflation.
    if len(value)>((limit+2)//3)*4+8:
        raise HTTPException(status_code=413,detail=f'{name} exceeds size limit')
    try:
        raw=base64.b64decode(value,validate=True)
    except (ValueError,base64.binascii.Error):
        raise HTTPException(status_code=422,detail=f'{name} must be valid base64')
    if len(raw)>limit:
        raise HTTPException(status_code=413,detail=f'{name} exceeds size limit')
    if not raw.startswith(signature):
        raise HTTPException(status_code=422,detail=f'{name} has invalid file signature')
    return raw


class EditParametersIn(BaseModel):
    prompt: str=Field(min_length=1,max_length=1500)
    shape_keys: dict[str,float]=Field(default_factory=dict,max_length=200)
    ranges: dict[str,list[float]]=Field(default_factory=dict,max_length=200)


ImageProvider = Literal['gateway', 'chatgpt_credits']
EncodedImage = Annotated[str, Field(min_length=10, max_length=12_000_000)]
OPENAI_API_BASE = 'https://api.openai.com/v1'


class ImageRequest(BaseModel):
    provider: ImageProvider = 'gateway'
    model: str | None = Field(default=None, min_length=1, max_length=160)


class PreviewIn(ImageRequest):
    white_png_base64: str=Field(min_length=10,max_length=12_000_000)
    reference_png_base64: str|None=Field(default=None,max_length=12_000_000)
    additional_png_base64: list[EncodedImage] = Field(default_factory=list, max_length=3)
    prompt: str=Field(default='',max_length=1500)


class ReferenceIn(ImageRequest):
    source_png_base64: str=Field(min_length=10,max_length=12_000_000)
    stage: str=Field(pattern='^(head|design|product)$')
    prompt: str=Field(default='',max_length=1500)
    additional_png_base64: list[EncodedImage] = Field(default_factory=list, max_length=6)


class ReferencePromptIn(BaseModel):
    stage: Literal['head', 'design', 'product']
    prompt: str = Field(default='', max_length=1500)


class Edit3DIn(BaseModel):
    prompt: str=Field(default='',max_length=1500)
    mesh_glb_base64: str=Field(min_length=10,max_length=28_000_000)
    edit_png_base64: str|None=Field(default=None,max_length=12_000_000)
    seed: int=Field(default=10,ge=0,le=2**32-1)
    steps: int=Field(default=30,ge=1,le=100)
    watertight_resolution: Literal[128,256,512]=512


def image_models() -> list[str]:
    default = os.getenv('OPENAI_IMAGE_MODEL', '').strip() or 'gpt-image-2'
    extras = os.getenv('EASYKIG_IMAGE_MODELS', '').split(',')
    return list(dict.fromkeys([default, *(model.strip() for model in extras if model.strip())]))


def is_openai_image_model(model: str) -> bool:
    return model == 'chatgpt-image-latest' or (model.startswith('gpt-image-') and model != 'gpt-image-1')


def image_credentials(provider: ImageProvider) -> tuple[str, str]:
    if provider == 'chatgpt_credits':
        key_var = 'OPENAI_SUBSCRIPTION_API_KEY'
        api_base = OPENAI_API_BASE
    else:
        key_var = 'OPENAI_IMAGE_API_KEY'
        api_base = os.getenv('OPENAI_IMAGE_API_BASE', OPENAI_API_BASE).rstrip('/')
    api_key = os.getenv(key_var, '').strip()
    if not api_key:
        raise HTTPException(status_code=503, detail=f'Set {key_var} to enable this image provider')
    if urlparse(api_base).scheme != 'https':
        raise HTTPException(status_code=500, detail='Image API base must be HTTPS')
    return api_base, api_key


async def discover_image_models(provider: ImageProvider) -> list[str]:
    api_base, key = image_credentials(provider)
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
            response = await client.get(api_base + '/models', headers={'Authorization': f'Bearer {key}'})
            response.raise_for_status()
            entries = response.json()['data']
        models = sorted({item['id'] for item in entries if is_openai_image_model(item['id'])})
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail='Image model catalog timed out') from exc
    except (httpx.HTTPError, KeyError, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(status_code=502, detail='Could not list OpenAI models. Check the linked project key and its model-read permission.') from exc
    preferred = 'gpt-image-2.5-sunburst'
    if preferred in models:
        models.remove(preferred)
        models.insert(0, preferred)
    return models


async def image_catalog(provider: ImageProvider) -> list[str]:
    if provider == 'chatgpt_credits':
        return await discover_image_models(provider)
    configured = image_models()
    if not os.getenv('OPENAI_IMAGE_API_KEY', '').strip():
        return configured
    try:
        discovered = await discover_image_models(provider)
    except HTTPException:
        # Some compatible image gateways expose edits without a model catalog.
        return configured
    return list(dict.fromkeys([*configured, *discovered]))


async def select_image_model(requested: str | None, provider: ImageProvider) -> str:
    if provider == 'chatgpt_credits' and requested is not None:
        if not is_openai_image_model(requested):
            raise HTTPException(status_code=422, detail='Choose an OpenAI image model')
        return requested
    if provider == 'gateway':
        configured = image_models()
        if requested is None:
            return configured[0]
        if requested in configured:
            return requested
        if not is_openai_image_model(requested):
            raise HTTPException(status_code=422, detail='Image model is not enabled on this gateway')
    allowed = await image_catalog(provider)
    if not allowed:
        raise HTTPException(status_code=503, detail='No image models available for this provider')
    if requested is None:
        return allowed[0]
    if requested not in allowed:
        raise HTTPException(status_code=422, detail='Image model is not enabled on this gateway')
    return requested


@app.get('/health')
async def health():
    models = image_models()
    return {'name':'easykig-gateway','status':'ok','version':app.version,
            'auth_mode':setting('AUTH_MODE', 'token'),
            'preview_enabled':bool(os.getenv('OPENAI_IMAGE_API_KEY')),
            'image_model': models[0], 'image_models': models,
            'image_catalog': True,
            'multi_reference_images': True,
            'image_providers': {'gateway': bool(os.getenv('OPENAI_IMAGE_API_KEY')),
                                'chatgpt_credits': bool(os.getenv('OPENAI_SUBSCRIPTION_API_KEY'))},
            'mesh_editor_enabled':bool(setting('EDIT3D_UPSTREAM_URL')),
            'mesh_editor_backend':edit3d_backend(),
            'mesh_editor_async':edit3d_backend()=='shapeup',
            'mesh_editor_requires_image':edit3d_backend()=='shapeup'}


@app.get('/v1/image/models', dependencies=[Depends(require_auth)])
async def list_image_models(provider: ImageProvider = 'gateway'):
    models = await image_catalog(provider)
    return {'provider': provider, 'image_models': models, 'image_model': models[0] if models else None}


@app.post('/v1/edit/parameters',dependencies=[Depends(require_auth)])
async def edit_parameters(inp: EditParametersIn):
    out,changes=propose_edits(inp.prompt,inp.shape_keys,inp.ranges)
    return {'shape_keys':out,'changes':changes,'mode':'rules',
            'message':('Rule-based edit; review visually.' if changes else
                       'No confident rule matched; unchanged. Install an AI editor for richer prompts.')}


@app.post('/v1/preview/finish',dependencies=[Depends(require_auth)])
async def finish_preview(inp: PreviewIn):
    white=decode_binary(inp.white_png_base64,PNGSIG,MAX_PNG,'white_png')
    ref=(decode_binary(inp.reference_png_base64,PNGSIG,MAX_PNG,'reference_png')
         if inp.reference_png_base64 else None)
    images = [white, ref] if ref is not None else [white]
    images.extend(decode_binary(value, PNGSIG, MAX_PNG, 'reference_image') for value in inp.additional_png_base64)
    image64=await provider_image_edit(
        images, finishing_prompt(inp.prompt),
        await select_image_model(inp.model, inp.provider), inp.provider,
    )
    return {'image_png_base64':image64,'mode':'image_edit',
            'warning':'Illustrative finish; cannot certify geometry or manufacturability'}


@app.post('/v1/reference/transform',dependencies=[Depends(require_auth)])
async def transform_reference(inp: ReferenceIn):
    source=decode_binary(inp.source_png_base64,PNGSIG,MAX_PNG,'reference_source')
    additional = [decode_binary(value, PNGSIG, MAX_PNG, 'reference_image') for value in inp.additional_png_base64]
    prompt = load_reference_prompt(inp.stage, inp.prompt)
    image64 = await provider_image_edit(
        [source, *additional], prompt, await select_image_model(inp.model, inp.provider), inp.provider,
    )
    return {'image_png_base64':image64,'stage':inp.stage,'mode':'image_edit',
            'warning':'Reference design only; not a 3D reconstruction'}


def load_reference_prompt(stage, details):
    try:
        return reference_prompt(stage, details)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=f'Reference preset for {stage} is unavailable') from exc


@app.post('/v1/image/reference-prompt', dependencies=[Depends(require_auth)])
async def get_reference_prompt(inp: ReferencePromptIn):
    return {'prompt': load_reference_prompt(inp.stage, inp.prompt)}


def upstream_binary(value, signature, limit, name):
    if not isinstance(value, str):
        raise HTTPException(status_code=502, detail=f'Upstream did not return {name}')
    try:
        decode_binary(value, signature, limit, name)
    except HTTPException as exc:
        raise HTTPException(status_code=502, detail=f'Invalid upstream response: {exc.detail}') from exc
    return value


async def provider_image_edit(images: list[bytes], prompt: str, model: str, provider: ImageProvider):
    """Minimal image-edit API adapter; requires a provider returning base64 PNG."""
    api_base, api_key = image_credentials(provider)
    field = 'image' if len(images) == 1 else 'image[]'
    files = [(field, (f'reference_{index}.png', image, 'image/png')) for index, image in enumerate(images, 1)]
    data={'model':model,'prompt':prompt,'size':'1024x1024'}
    async with httpx.AsyncClient(timeout=180.0,follow_redirects=False) as client:
        try:
            response=await client.post(api_base+'/images/edits',
                                       headers={'Authorization':'Bearer '+api_key},
                                       files=files,data=data)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (401, 403):
                raise HTTPException(status_code=502, detail=f'Image API rejected the provider credentials or model access (HTTP {status})')
            if status == 429:
                try:
                    code = exc.response.json()['error']['code']
                except (KeyError, TypeError, ValueError):
                    code = None
                detail = ('Image provider quota exhausted (HTTP 429). Check the provider billing and quota.'
                          if code in ('insufficient_quota', 'billing_hard_limit_reached', 'credit_balance_exhausted')
                          else 'Image provider rate limit or quota reached (HTTP 429). Check the provider limits.')
                raise HTTPException(status_code=502, detail=detail) from exc
            raise HTTPException(status_code=502, detail=f'Image API returned HTTP {status}')
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=504, detail='Image provider timed out') from exc
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502,detail=f'Image provider connection failed: {str(exc)[:160]}')
    try:
        image64=response.json()['data'][0]['b64_json']
    except (KeyError,IndexError,TypeError,ValueError):
        raise HTTPException(status_code=502,detail='Image API did not return b64_json; check model/provider')
    return upstream_binary(image64, PNGSIG, 24*1024*1024, 'generated_png')


@app.post('/v1/edit3d',dependencies=[Depends(require_auth)])
async def edit_mesh(inp: Edit3DIn):
    if edit3d_backend() == 'shapeup':
        raise HTTPException(409, detail='ShapeUp uses image-conditioned async jobs. Update the add-on and use /v1/edit3d/jobs.')
    if not inp.prompt.strip():
        raise HTTPException(422, detail='The generic 3D editor requires a text prompt')
    decode_binary(inp.mesh_glb_base64,b'glTF',MAX_GLB,'mesh_glb')
    upstream=setting('EDIT3D_UPSTREAM_URL','').strip()
    if not upstream:
        raise HTTPException(status_code=501,detail='Remote 3D editor not connected. Set EASYKIG_EDIT3D_UPSTREAM_URL.')
    parsed=urlparse(upstream)
    if parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in ('127.0.0.1','localhost')):
        raise HTTPException(status_code=500,detail='3D upstream must be HTTPS or a localhost tunnel')
    # Provider-agnostic adapter: caller deploys an edit service compatible with this JSON contract.
    async with httpx.AsyncClient(timeout=300.0,follow_redirects=False) as client:
        try:
            headers={}
            upstream_key=setting('EDIT3D_UPSTREAM_TOKEN','')
            if upstream_key:
                headers['Authorization']='Bearer '+upstream_key
            payload={'prompt':inp.prompt,'mesh_glb_base64':inp.mesh_glb_base64}
            resp=await client.post(upstream,headers=headers,json=payload)
            resp.raise_for_status()
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=504, detail='3D upstream timed out') from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502,detail=f'3D upstream error: {str(exc)[:200]}')
    try:
        edited = resp.json()['mesh_glb_base64']
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail='3D editor did not return mesh_glb_base64') from exc
    return {'mesh_glb_base64': upstream_binary(edited, b'glTF', MAX_GLB, 'edited_glb'), 'mode': 'upstream'}


def shapeup_backend():
    if edit3d_backend() != 'shapeup':
        raise HTTPException(501, 'Async 3D jobs require EASYKIG_EDIT3D_BACKEND=shapeup')
    return ShapeUp()


@app.get('/v1/edit3d/health',dependencies=[Depends(require_auth)])
async def edit3d_health():
    return await shapeup_backend().readiness()


@app.post('/v1/edit3d/jobs',status_code=202,dependencies=[Depends(require_auth)])
async def submit_edit3d_job(inp: Edit3DIn):
    service=shapeup_backend()
    mesh=decode_binary(inp.mesh_glb_base64,b'glTF',MAX_GLB,'mesh_glb')
    if not inp.edit_png_base64:
        raise HTTPException(422, 'ShapeUp requires a target edit image; choose a generated preview or PNG image')
    image=decode_binary(inp.edit_png_base64,PNGSIG,MAX_PNG,'edit_png')
    return await service.submit(mesh,image,seed=inp.seed,steps=inp.steps,
                                watertight_resolution=inp.watertight_resolution)


@app.get('/v1/edit3d/jobs/{job_id}',dependencies=[Depends(require_auth)])
async def edit3d_job_status(job_id: str):
    return await shapeup_backend().status(job_id)


@app.get('/v1/edit3d/jobs/{job_id}/result',dependencies=[Depends(require_auth)])
async def edit3d_job_result(job_id: str):
    raw=await shapeup_backend().result(job_id)
    return Response(raw,media_type='model/gltf-binary',
                    headers={'Content-Disposition':f'attachment; filename="easykig-{job_id}.glb"'})
