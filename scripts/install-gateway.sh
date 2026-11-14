#!/usr/bin/env bash
# Install this checkout beside /data/ShapeUp on the current SSH container.
set -euo pipefail
case "${1:-}" in
  '') export EASYKIG_INSTALL_AUTH_MODE='' ;;
  --ssh-auth) export EASYKIG_INSTALL_AUTH_MODE=ssh ;;
  *) echo 'Usage: install-gateway.sh [--ssh-auth]' >&2; exit 1 ;;
esac
task_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$(id -u)" != 0 || "$task_root" != /data/EasyKig ]]; then
  echo 'Run as root from the /data/EasyKig checkout.' >&2
  exit 1
fi
cd "$task_root"
if [[ ! -x "$task_root/.venv/bin/python" ]]; then
  apt-get update
  apt-get install -y python3.10-venv
  /usr/bin/python3.10 -m venv "$task_root/.venv"
fi
"$task_root/.venv/bin/python" -m pip install -r "$task_root/server/requirements.txt"
mkdir -p "$task_root/runtime"
"$task_root/.venv/bin/python" - <<'PY'
from pathlib import Path
import os
import secrets
from dotenv import dotenv_values, set_key
root=Path('/data/EasyKig')
env=root/'server/.env'
if not env.exists():
    env.write_text((root/'server/.env.example').read_text())
    os.chmod(env,0o600)
    for key,value in {
        'EASYKIG_EDIT3D_BACKEND':'shapeup',
        'EASYKIG_EDIT3D_UPSTREAM_URL':'http://127.0.0.1:8000',
        'EASYKIG_EDIT3D_UPSTREAM_TOKEN_FILE':'/data/ShapeUp/runtime/api-token',
        'EASYKIG_EDIT3D_JOB_DIR':'/data/EasyKig/runtime/edit3d-jobs',
        'EASYKIG_HOST':'127.0.0.1','EASYKIG_PORT':'8001',
    }.items():set_key(env,key,value)
values=dotenv_values(env)
if os.environ['EASYKIG_INSTALL_AUTH_MODE']=='ssh':
    set_key(env,'EASYKIG_AUTH_MODE','ssh')
    set_key(env,'EASYKIG_HOST','127.0.0.1')
token=values.get('EASYKIG_SERVER_TOKEN','')
if not token or token=='choose-a-long-random-token':
    token=secrets.token_urlsafe(32)
    set_key(env,'EASYKIG_SERVER_TOKEN',token)
token_path=root/'runtime/api-token'
fd=os.open(token_path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
with os.fdopen(fd,'w') as f:f.write(token+'\n')
os.chmod(token_path,0o600)
PY
if ! command -v supervisorctl >/dev/null; then
  apt-get update
  apt-get install -y supervisor
fi
install -m 0644 "$task_root/server/easykig.supervisor.conf" /etc/supervisor/conf.d/easykig.conf
# Reuse ShapeUp's verified container startup hook and detached Supervisor.
/usr/local/sbin/shapeup-ensure-supervisor
supervisorctl reread
supervisorctl update
if [[ "$EASYKIG_INSTALL_AUTH_MODE" == ssh ]]; then
  supervisorctl restart easykig
fi
state="$(supervisorctl status easykig | awk '{print $2}')" || true
case "$state" in
  STOPPED|EXITED|FATAL) supervisorctl start easykig ;;
esac
supervisorctl status easykig || true
