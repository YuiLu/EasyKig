"""CPU-only bridge to ShapeUp's persistent inference queue."""
import asyncio
import base64
import io
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

MAX_GLB = 20 * 1024 * 1024
JOB_ID = re.compile(r'^[0-9a-f]{32}$')


def setting(name, default=''):
    return os.getenv('EASYKIG_' + name, os.getenv('KIGSHELL_' + name, default))


def backend():
    value = setting('EDIT3D_BACKEND', 'generic').strip().lower()
    if value not in ('generic', 'shapeup'):
        raise HTTPException(503, 'EASYKIG_EDIT3D_BACKEND must be generic or shapeup')
    return value


def validate_job_id(value):
    if not isinstance(value, str) or not JOB_ID.fullmatch(value):
        raise HTTPException(422, 'Invalid 3D job ID')
    return value


def mesh_transform(raw):
    """Inverse of ShapeUp's bbox centering and max-extent normalization."""
    import numpy as np
    import trimesh
    try:
        scene = trimesh.load(io.BytesIO(raw), file_type='glb', force='scene')
        if not scene.geometry or not any(len(g.faces) for g in scene.geometry.values() if hasattr(g, 'faces')):
            raise ValueError('No mesh faces')
        bounds = np.asarray(scene.bounds, dtype=float)
        half_extent = float(np.max(bounds[1] - bounds[0]) / 2)
        if not np.isfinite(bounds).all() or not np.isfinite(half_extent) or half_extent <= 0:
            raise ValueError('Empty bounds')
        return {'center': ((bounds[0] + bounds[1]) / 2).tolist(), 'half_extent': half_extent}
    except Exception as exc:
        raise HTTPException(422, 'Source GLB must contain a valid, non-empty mesh') from exc


def restore_mesh(raw, transform):
    import numpy as np
    import trimesh
    try:
        scene = trimesh.load(io.BytesIO(raw), file_type='glb', force='scene')
        if not scene.geometry:
            raise ValueError('No output mesh')
        matrix = np.eye(4)
        matrix[:3, :3] *= transform['half_extent']
        matrix[:3, 3] = transform['center']
        scene.apply_transform(matrix)
        result = scene.export(file_type='glb')
        if len(result) > MAX_GLB:
            raise HTTPException(502, 'Edited GLB exceeds 20 MiB; reduce model complexity')
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, 'ShapeUp returned an invalid GLB') from exc


class ShapeUp:
    def __init__(self):
        self.url = setting('EDIT3D_UPSTREAM_URL').strip().rstrip('/')
        parsed = urlparse(self.url)
        local = parsed.hostname in ('127.0.0.1', 'localhost', '::1')
        if not self.url:
            raise HTTPException(501, 'Set EASYKIG_EDIT3D_UPSTREAM_URL to the ShapeUp service root')
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or
                (parsed.scheme == 'http' and not local) or parsed.username or parsed.password or
                parsed.query or parsed.fragment):
            raise HTTPException(503, 'ShapeUp URL must use HTTPS or a localhost SSH tunnel, without credentials or query')
        self.token = setting('EDIT3D_UPSTREAM_TOKEN').strip()
        token_file = setting('EDIT3D_UPSTREAM_TOKEN_FILE').strip()
        if not self.token and token_file:
            try:
                self.token = Path(token_file).read_text().strip()
            except OSError as exc:
                raise HTTPException(503, 'Cannot read the ShapeUp token file') from exc
        if not self.token:
            raise HTTPException(503, 'Configure the ShapeUp token or token file on the gateway')
        self.headers = {'Authorization': 'Bearer ' + self.token}
        self.jobs_dir = Path(setting('EDIT3D_JOB_DIR', 'runtime/edit3d-jobs'))

    def _metadata(self, job_id):
        validate_job_id(job_id)
        try:
            return json.loads((self.jobs_dir / (job_id + '.json')).read_text())
        except FileNotFoundError as exc:
            raise HTTPException(404, '3D job is not known to this gateway') from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(503, 'Cannot read the stored 3D job') from exc

    async def _request(self, method, path, **kwargs):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=10),
                                         follow_redirects=False, trust_env=False) as client:
                response = await client.request(method, self.url + path, headers=self.headers, **kwargs)
        except httpx.TimeoutException as exc:
            raise HTTPException(504, 'ShapeUp request timed out; an accepted job can be resumed by ID') from exc
        except httpx.HTTPError as exc:
            raise HTTPException(503, 'Cannot connect to ShapeUp; check its service and gateway configuration') from exc
        if response.status_code in (401, 403):
            raise HTTPException(502, 'ShapeUp rejected the upstream token; check gateway credentials')
        if response.status_code == 429:
            raise HTTPException(429, 'ShapeUp GPU queue is full; retry later')
        if response.status_code == 503:
            raise HTTPException(503, 'ShapeUp is not ready; check GPU access, dependencies and weights')
        if response.status_code == 404:
            raise HTTPException(404, 'ShapeUp job was not found')
        if response.status_code in (413, 422):
            raise HTTPException(response.status_code, 'ShapeUp rejected the uploaded mesh, image or parameters')
        if not 200 <= response.status_code < 300:
            raise HTTPException(502, f'ShapeUp returned HTTP {response.status_code}')
        return response

    @staticmethod
    def _json(response):
        try:
            value = response.json()
            if not isinstance(value, dict):
                raise ValueError
            return value
        except (TypeError, ValueError) as exc:
            raise HTTPException(502, 'ShapeUp returned invalid JSON') from exc

    async def readiness(self):
        data = self._json(await self._request('GET', '/readyz'))
        if not data.get('ready'):
            raise HTTPException(503, 'ShapeUp is not ready')
        return {'backend': 'shapeup', **data}

    async def submit(self, mesh, image, *, seed=10, steps=30, watertight_resolution=512):
        transform = await asyncio.to_thread(mesh_transform, mesh)
        data = self._json(await self._request('POST', '/jobs',
            files={'mesh': ('source.glb', mesh, 'model/gltf-binary'),
                   'image': ('edit.png', image, 'image/png')},
            data={'seed': str(seed), 'steps': str(steps),
                  'watertight_resolution': str(watertight_resolution)}))
        try:
            job_id = validate_job_id(data['id'])
        except (KeyError, HTTPException) as exc:
            raise HTTPException(502, 'ShapeUp did not return a valid job ID') from exc
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        metadata = {'id': job_id, 'created_at': time.time(), 'transform': transform}
        path = self.jobs_dir / (job_id + '.json')
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(metadata))
        temp.replace(path)
        return {'id': job_id, 'status': data.get('status', 'queued'), 'backend': 'shapeup'}

    async def status(self, job_id):
        self._metadata(job_id)
        data = self._json(await self._request('GET', '/jobs/' + job_id))
        if data.get('status') not in ('queued', 'running', 'succeeded', 'failed'):
            raise HTTPException(502, 'ShapeUp returned an unknown job state')
        result = {key: data[key] for key in ('id', 'status', 'created_at', 'started_at', 'finished_at', 'error') if key in data}
        result['backend'] = 'shapeup'
        return result

    async def result(self, job_id):
        metadata = self._metadata(job_id)
        status = await self.status(job_id)
        if status['status'] != 'succeeded':
            raise HTTPException(409, '3D result is not ready')
        # Bound the stream before buffering it or loading the GLB on CPU.
        try:
            async with httpx.AsyncClient(timeout=120, follow_redirects=False, trust_env=False) as client:
                async with client.stream('GET', self.url + '/jobs/' + job_id + '/result', headers=self.headers) as response:
                    if response.status_code != 200:
                        raise HTTPException(502, f'ShapeUp result returned HTTP {response.status_code}')
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > MAX_GLB:
                            raise HTTPException(502, 'Edited GLB exceeds 20 MiB')
        except httpx.TimeoutException as exc:
            raise HTTPException(504, 'ShapeUp result download timed out; resume this job') from exc
        except httpx.HTTPError as exc:
            raise HTTPException(502, 'ShapeUp result download failed; resume this job') from exc
        return await asyncio.to_thread(restore_mesh, bytes(chunks), metadata['transform'])
