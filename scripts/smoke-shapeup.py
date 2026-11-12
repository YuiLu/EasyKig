"""Exercise the Blender workflow through a real gateway and a fake CPU-only ShapeUp.

Usage: .venv/bin/python scripts/smoke-shapeup.py --blender /path/to/blender
"""
import argparse
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time

import numpy as np
import trimesh
import uvicorn

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
JOB='f'*32


class Upstream(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass

    def reply(self,status,body,kind='application/json'):
        raw=json.dumps(body).encode() if kind=='application/json' else body
        self.send_response(status)
        self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        assert self.headers['Authorization']=='Bearer fake-shapeup-token'
        assert self.path=='/jobs'
        body=self.rfile.read(int(self.headers['Content-Length']))
        message=BytesParser(policy=policy.default).parsebytes(
            ('Content-Type: '+self.headers['Content-Type']+'\r\n\r\n').encode()+body)
        fields={part.get_param('name',header='content-disposition'):part.get_payload(decode=True)
                for part in message.iter_parts()}
        assert fields['image'].startswith(b'\x89PNG')
        scene=trimesh.load(io.BytesIO(fields['mesh']),file_type='glb',force='scene')
        bounds=scene.bounds
        matrix=np.eye(4)
        factor=2/np.max(bounds[1]-bounds[0])
        matrix[:3,:3]*=factor
        matrix[:3,3]=-bounds.mean(axis=0)*factor
        scene.apply_transform(matrix)
        self.server.result=scene.export(file_type='glb')
        self.server.submissions+=1
        self.reply(202,{'id':JOB,'status':'queued'})

    def do_GET(self):
        assert self.headers['Authorization']=='Bearer fake-shapeup-token'
        if self.path=='/readyz':
            self.reply(200,{'ready':True})
        elif self.path.endswith('/result'):
            self.reply(200,self.server.result,'model/gltf-binary')
        else:
            self.server.polls+=1
            state='running' if self.server.polls==1 else 'succeeded'
            self.reply(200,{'id':JOB,'status':state})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blender',required=True)
    parser.add_argument('--zip',help='Validate the built extension in Blender\'s bl_ext namespace')
    args=parser.parse_args()
    output=ROOT/'runtime/blender-smoke'
    output.mkdir(parents=True,exist_ok=True)
    upstream=ThreadingHTTPServer(('127.0.0.1',0),Upstream)
    upstream.submissions=0
    upstream.polls=0
    upstream_thread=threading.Thread(target=upstream.serve_forever,daemon=True)
    upstream_thread.start()
    with tempfile.TemporaryDirectory(prefix='easykig-smoke-') as temp:
        os.environ.update(EASYKIG_SERVER_TOKEN='blender-smoke',EASYKIG_EDIT3D_BACKEND='shapeup',
            EASYKIG_EDIT3D_UPSTREAM_URL=f'http://127.0.0.1:{upstream.server_port}',
            EASYKIG_EDIT3D_UPSTREAM_TOKEN='fake-shapeup-token',EASYKIG_EDIT3D_JOB_DIR=temp)
        from server.app import app
        sock=socket.socket()
        sock.bind(('127.0.0.1',0))
        port=sock.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(app,log_level='warning'))
        thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True)
        thread.start()
        try:
            deadline=time.monotonic()+10
            while not server.started:
                if time.monotonic()>deadline:
                    raise RuntimeError('Test gateway failed to start')
                time.sleep(.05)
            env={**os.environ,'EASYKIG_SMOKE_DIR':str(output),'EASYKIG_SMOKE_URL':f'http://127.0.0.1:{port}'}
            if args.zip:
                env['EASYKIG_ADDON_ZIP']=str(Path(args.zip).resolve())
            with (output/'blender.log').open('w') as log:
                proc=subprocess.run([args.blender,'--background','--factory-startup','--online-mode',
                    '--python-exit-code','1','--python',str(ROOT/'scripts/blender-shapeup-smoke.py')],
                    env=env,stdout=log,stderr=subprocess.STDOUT,timeout=120)
            if proc.returncode:
                raise RuntimeError((output/'blender.log').read_text()[-6000:])
            assert upstream.submissions==1,'Resume must not submit another GPU job'
            report=json.loads((output/'blender-smoke.json').read_text())
            report['upstream_submissions']=upstream.submissions
            report['mock_upstream']=True
            (output/'blender-smoke.json').write_text(json.dumps(report,indent=2))
            print(json.dumps(report,indent=2))
        finally:
            server.should_exit=True
            thread.join(5)
            upstream.shutdown()
            upstream.server_close()


if __name__=='__main__':
    main()
