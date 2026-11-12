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
    uvicorn.run('server.app:app', host=os.getenv('EASYKIG_HOST', '127.0.0.1'),
                port=int(os.getenv('EASYKIG_PORT', '8001')), workers=1,
                limit_concurrency=16, timeout_graceful_shutdown=20)
