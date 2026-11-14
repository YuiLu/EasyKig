"""Resumable 3D jobs. Network workers use no Blender API or GPU libraries."""
import base64
import json
from pathlib import Path
import queue
import re
import threading
import time

from .http_client import http_bytes, http_json, normalize_url

MAX_GLB = 20 * 1024 * 1024


class MeshJobClient:
    def __init__(self, server_url, token, timeout=60):
        self.url = normalize_url(server_url)
        self.token = token
        self.timeout = timeout

    def json(self, path, payload=None, *, authenticated=True):
        headers = {'Accept': 'application/json'}
        if authenticated and self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        data = None
        if payload is not None:
            data = json.dumps(payload).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        return http_json(self.url + path, self.timeout, headers, data)

    def result(self, job_id):
        headers = {'Authorization': 'Bearer ' + self.token} if self.token else {}
        raw = http_bytes(self.url + '/v1/edit3d/jobs/' + job_id + '/result', self.timeout,
                         headers, limit=MAX_GLB)
        if not raw.startswith(b'glTF'):
            raise ValueError('Remote server did not return a GLB')
        return raw


class MeshJobWorker:
    def __init__(self, client, result_path, receipt_path, *, total_timeout=7200, poll_interval=2):
        self.client = client
        self.result_path = Path(result_path)
        self.receipt_path = Path(receipt_path)
        self.total_timeout = total_timeout
        self.poll_interval = poll_interval
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.thread = None

    def start(self, payload=None, job_id=None):
        self.thread = threading.Thread(target=self._run, args=(payload, job_id), daemon=True)
        self.thread.start()
        return self

    @staticmethod
    def job_id(value):
        if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{32}', value):
            raise ValueError('Server did not return a valid 3D job ID')
        return value

    def _run(self, payload, job_id):
        try:
            if job_id is None:
                info = self.client.json('/health', authenticated=False)
                if self.stop.is_set():
                    return
                if not info.get('mesh_editor_enabled'):
                    raise RuntimeError('3D editing is not configured on the EasyKig gateway')
                if info.get('mesh_editor_async'):
                    if not payload.get('edit_png_base64'):
                        raise ValueError('ShapeUp needs a target image. Choose Finished, a reference result, or an image file.')
                    job = self.client.json('/v1/edit3d/jobs', payload)
                    job_id = self.job_id(job.get('id'))
                    # Save the receipt before honoring Stop Waiting, even if the
                    # user stopped while the upload was in flight. No token is saved.
                    self.receipt_path.parent.mkdir(parents=True, exist_ok=True)
                    self.receipt_path.write_text(json.dumps({'server_url': self.client.url, 'id': job_id}))
                    self.events.put(('submitted', job_id))
                else:
                    result = self.client.json('/v1/edit3d', payload)
                    raw = base64.b64decode(result['mesh_glb_base64'], validate=True)
                    self._save_result(raw)
                    return
            job_id = self.job_id(job_id)
            deadline = time.monotonic() + self.total_timeout
            while not self.stop.is_set():
                if time.monotonic() > deadline:
                    raise RuntimeError('Stopped waiting after the 3D job timeout. The server job can be resumed by ID.')
                job = self.client.json('/v1/edit3d/jobs/' + job_id)
                self.events.put(('status', job.get('status', 'unknown')))
                if job.get('status') == 'failed':
                    raise RuntimeError(job.get('error') or '3D generation failed')
                if job.get('status') == 'succeeded':
                    if self.stop.is_set():
                        return
                    self.events.put(('status', 'downloading'))
                    self._save_result(self.client.result(job_id))
                    return
                if job.get('status') not in ('queued', 'running'):
                    raise RuntimeError('Server returned an unknown 3D job state')
                self.stop.wait(self.poll_interval)
        except Exception as exc:
            self.events.put(('error', str(exc)))
        finally:
            self.events.put(('worker_done', None))

    def _save_result(self, raw):
        if not raw.startswith(b'glTF') or len(raw) > MAX_GLB:
            raise ValueError('Returned GLB is invalid or exceeds 20 MiB')
        self.result_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.result_path.with_suffix('.part')
        temp.write_bytes(raw)
        temp.replace(self.result_path)
        self.events.put(('done', str(self.result_path)))
