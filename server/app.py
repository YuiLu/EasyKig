"""EasyKig gateway for component mesh editing and resumable ShapeUp jobs."""
import base64
import hmac
import ipaddress
import os
from typing import Literal
from urllib.parse import urlparse
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
import httpx

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


class Edit3DIn(BaseModel):
    prompt: str=Field(default='',max_length=1500)
    mesh_glb_base64: str=Field(min_length=10,max_length=28_000_000)
    edit_png_base64: str|None=Field(default=None,max_length=12_000_000)
    seed: int=Field(default=10,ge=0,le=2**32-1)
    steps: int=Field(default=30,ge=1,le=100)
    watertight_resolution: Literal[128,256,512]=512


@app.get('/health')
@app.get('/v1/health', dependencies=[Depends(require_auth)])
async def health():
    backend = edit3d_backend()
    return {'name': 'easykig-gateway', 'status': 'ok', 'version': app.version,
            'auth_mode': setting('AUTH_MODE', 'token'), 'authenticated_health': True,
            'mesh_editor_enabled': bool(setting('EDIT3D_UPSTREAM_URL')),
            'mesh_editor_backend': backend, 'mesh_editor_async': backend == 'shapeup',
            'mesh_editor_requires_image': backend == 'shapeup', 'mesh_editor_text': False}


def upstream_binary(value, signature, limit, name):
    if not isinstance(value, str):
        raise HTTPException(status_code=502, detail=f'Upstream did not return {name}')
    try:
        decode_binary(value, signature, limit, name)
    except HTTPException as exc:
        raise HTTPException(status_code=502, detail=f'Invalid upstream response: {exc.detail}') from exc
    return value


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
        raise HTTPException(422, 'ShapeUp requires a target edit image; choose a component reference PNG')
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
