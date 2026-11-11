"""EasyKig remote gateway (FastAPI).

Contracts:
  GET  /health
  POST /v1/edit/parameters
  POST /v1/preview/finish
  POST /v1/edit3d

Preview requires OPENAI_IMAGE_API_KEY; 3D mesh editing requires a separately deployed
compatible upstream service at EASYKIG_EDIT3D_UPSTREAM_URL. Both are opt-in.
"""
import base64
import hmac
import os
from typing import Annotated
from urllib.parse import urlparse
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
import httpx

from .prompts import finishing_prompt, reference_prompt
from .shape_rules import propose_edits

MAX_PNG=8*1024*1024
MAX_GLB=20*1024*1024
PNGSIG=b'\x89PNG\r\n\x1a\n'

app=FastAPI(title='EasyKig Remote Gateway',version='0.1.0',docs_url=None,redoc_url=None)


def setting(name: str, default: str = '') -> str:
    return os.getenv(f'EASYKIG_{name}', os.getenv(f'KIGSHELL_{name}', default))


def require_auth(authorization: str|None=Header(default=None)):
    expected=setting('SERVER_TOKEN','')
    if not expected:
        # A local-only dev setup may omit token, but deployment must set token.
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


class PreviewIn(BaseModel):
    white_png_base64: str=Field(min_length=10,max_length=12_000_000)
    reference_png_base64: str|None=Field(default=None,max_length=12_000_000)
    prompt: str=Field(default='',max_length=1500)


class ReferenceIn(BaseModel):
    source_png_base64: str=Field(min_length=10,max_length=12_000_000)
    stage: str=Field(pattern='^(head|design|product)$')
    prompt: str=Field(default='',max_length=1500)
    additional_png_base64: list[Annotated[str, Field(min_length=10, max_length=12_000_000)]] = Field(
        default_factory=list, max_length=3
    )


class Edit3DIn(BaseModel):
    prompt: str=Field(min_length=1,max_length=1500)
    mesh_glb_base64: str=Field(min_length=10,max_length=28_000_000)


@app.get('/health')
async def health():
    return {'name':'easykig-gateway','status':'ok','version':'0.1.0',
            'preview_enabled':bool(os.getenv('OPENAI_IMAGE_API_KEY')),
            'mesh_editor_enabled':bool(setting('EDIT3D_UPSTREAM_URL'))}


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
    image64=await provider_image_edit([white, ref] if ref is not None else [white], finishing_prompt(inp.prompt))
    return {'image_png_base64':image64,'mode':'image_edit',
            'warning':'Illustrative finish; cannot certify geometry or manufacturability'}


@app.post('/v1/reference/transform',dependencies=[Depends(require_auth)])
async def transform_reference(inp: ReferenceIn):
    source=decode_binary(inp.source_png_base64,PNGSIG,MAX_PNG,'reference_source')
    additional = [decode_binary(value, PNGSIG, MAX_PNG, 'reference_image') for value in inp.additional_png_base64]
    try:
        prompt = reference_prompt(inp.stage, inp.prompt)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=f'Reference preset for {inp.stage} is unavailable') from exc
    image64 = await provider_image_edit([source, *additional], prompt)
    return {'image_png_base64':image64,'stage':inp.stage,'mode':'image_edit',
            'warning':'Reference design only; not a 3D reconstruction'}


def upstream_binary(value, signature, limit, name):
    if not isinstance(value, str):
        raise HTTPException(status_code=502, detail=f'Upstream did not return {name}')
    try:
        decode_binary(value, signature, limit, name)
    except HTTPException as exc:
        raise HTTPException(status_code=502, detail=f'Invalid upstream response: {exc.detail}') from exc
    return value


async def provider_image_edit(images: list[bytes], prompt: str):
    """Minimal image-edit API adapter; requires a provider returning base64 PNG."""
    api_key=os.getenv('OPENAI_IMAGE_API_KEY','')
    if not api_key:
        raise HTTPException(status_code=503,detail='Set OPENAI_IMAGE_API_KEY to enable AI image previews')
    api_base=os.getenv('OPENAI_IMAGE_API_BASE','https://api.openai.com/v1').rstrip('/')
    if urlparse(api_base).scheme!='https':
        raise HTTPException(status_code=500,detail='Image API base must be HTTPS')
    model=os.getenv('OPENAI_IMAGE_MODEL','gpt-image-2')
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
            resp=await client.post(upstream,headers=headers,json=inp.model_dump())
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
