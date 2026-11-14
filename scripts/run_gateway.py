"""Run the local EasyKig gateway without loading any GPU models."""
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if __name__ == '__main__':
    load_dotenv(ROOT / 'server/.env')
    host = os.getenv('EASYKIG_HOST', '127.0.0.1')
    if os.getenv('EASYKIG_AUTH_MODE', 'token') == 'ssh' and host not in ('127.0.0.1', '::1', 'localhost'):
        raise SystemExit('SSH authentication requires EASYKIG_HOST=127.0.0.1, ::1 or localhost')
    uvicorn.run('server.app:app', host=host,
                port=int(os.getenv('EASYKIG_PORT', '8001')), workers=1,
                proxy_headers=False, limit_concurrency=16, timeout_graceful_shutdown=20)
