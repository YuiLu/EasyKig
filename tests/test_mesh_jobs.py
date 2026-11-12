import base64
import json
from pathlib import Path
import subprocess
import sys

from easykig.mesh_jobs import MeshJobWorker

JOB = 'c' * 32


class Client:
    url = 'http://127.0.0.1:8001'

    def __init__(self):
        self.calls = []
        self.states = iter(['queued', 'running', 'succeeded'])

    def json(self, path, payload=None, **kwargs):
        self.calls.append((path, payload))
        if path == '/health':
            return {'mesh_editor_enabled': True, 'mesh_editor_async': True}
        if path == '/v1/edit3d/jobs':
            return {'id': JOB, 'status': 'queued'}
        return {'id': JOB, 'status': next(self.states)}

    def result(self, job_id):
        assert job_id == JOB
        return b'glTFtest-result'


def test_async_worker_receipt_and_result(tmp_path):
    client = Client()
    worker = MeshJobWorker(client, tmp_path / 'result.glb', tmp_path / 'receipt.json', poll_interval=.001)
    worker.start({'edit_png_base64': 'image'})
    worker.thread.join(3)
    assert not worker.thread.is_alive()
    assert worker.result_path.read_bytes() == b'glTFtest-result'
    assert json.loads(worker.receipt_path.read_text()) == {'server_url': client.url, 'id': JOB}
    events = list(worker.events.queue)
    assert ('submitted', JOB) in events
    assert [v for kind, v in events if kind == 'status'] == ['queued', 'running', 'succeeded', 'downloading']
    assert not any(kind == 'error' for kind, _ in events)


def test_resume_does_not_submit_another_job(tmp_path):
    client = Client()
    client.states = iter(['succeeded'])
    worker = MeshJobWorker(client, tmp_path / 'result.glb', tmp_path / 'receipt.json')
    worker.start(job_id=JOB)
    worker.thread.join(3)
    assert [p for p, _ in client.calls] == ['/v1/edit3d/jobs/' + JOB]
    assert worker.result_path.exists()


def test_stopping_during_upload_still_saves_job_receipt(tmp_path):
    client = Client()
    original = client.json
    worker = MeshJobWorker(client, tmp_path / 'result.glb', tmp_path / 'receipt.json')

    def stop_after_submission(path, payload=None, **kwargs):
        result = original(path, payload, **kwargs)
        if path == '/v1/edit3d/jobs':
            worker.stop.set()
        return result

    client.json = stop_after_submission
    worker.start({'edit_png_base64': 'image'})
    worker.thread.join(3)
    assert json.loads(worker.receipt_path.read_text())['id'] == JOB
    assert not worker.result_path.exists()


def test_missing_target_image_is_not_submitted(tmp_path):
    client = Client()
    worker = MeshJobWorker(client, tmp_path / 'result.glb', tmp_path / 'receipt.json')
    worker.start({})
    worker.thread.join(3)
    assert [p for p, _ in client.calls] == ['/health']
    assert any(kind == 'error' and 'target image' in value for kind, value in worker.events.queue)


def test_legacy_3d_editor_still_works(tmp_path):
    class Legacy(Client):
        def json(self, path, payload=None, **kwargs):
            if path == '/health':
                return {'mesh_editor_enabled': True}
            assert path == '/v1/edit3d'
            return {'mesh_glb_base64': base64.b64encode(b'glTFlegacy').decode()}
    worker = MeshJobWorker(Legacy(), tmp_path / 'result.glb', tmp_path / 'receipt.json')
    worker.start({'prompt': 'edit'})
    worker.thread.join(3)
    assert worker.result_path.read_bytes() == b'glTFlegacy'


def test_worker_module_is_independent_of_blender_and_torch():
    result = subprocess.run([sys.executable, '-c',
        'import sys; from easykig.mesh_jobs import MeshJobWorker; assert "bpy" not in sys.modules; assert "torch" not in sys.modules'],
        cwd=Path(__file__).parents[1], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
