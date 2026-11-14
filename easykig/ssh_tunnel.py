"""An owned OpenSSH local forward. Uses the user's SSH config and agent."""
import shutil
import socket
import subprocess
import tempfile
import threading
from pathlib import Path


def ssh_arguments(host, port, user, identity, local_port, remote_host, remote_port):
    for name, value in (('SSH Host', host), ('SSH User', user), ('Remote Host', remote_host)):
        if value.startswith('-') or any(character.isspace() or ord(character) < 32 for character in value):
            raise ValueError(f'{name} contains unsupported characters')
    if not host or not remote_host:
        raise ValueError('Set SSH Host and Remote Host in EasyKig preferences')
    if not 0 <= port <= 65535 or not all(1 <= value <= 65535 for value in (local_port, remote_port)):
        raise ValueError('SSH tunnel ports must be between 1 and 65535; SSH Port may be 0 to use SSH config')
    # Brackets keep IPv6 destinations unambiguous in -L's colon-separated syntax.
    destination = f'[{remote_host}]' if ':' in remote_host else remote_host
    arguments = ['-N', '-T', '-o', 'BatchMode=yes', '-o', 'ExitOnForwardFailure=yes',
                 '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=15',
                 '-o', 'ServerAliveCountMax=3']
    if port:
        arguments.extend(['-p', str(port)])
    if user:
        arguments.extend(['-l', user])
    if identity:
        arguments.extend(['-i', identity])
    arguments.extend(['-L', f'127.0.0.1:{local_port}:{destination}:{remote_port}', host])
    return arguments


class SshTunnel:
    def __init__(self):
        self.process = None
        self.status = 'Disconnected'
        self._errors = None
        self._monitor = None
        self._stop = threading.Event()

    def start(self, *, host, port=0, user='', identity='', local_port=8001,
              remote_host='127.0.0.1', remote_port=8001):
        arguments = ssh_arguments(host, port, user, identity, local_port, remote_host, remote_port)
        executable = shutil.which('ssh')
        if not executable:
            raise RuntimeError('OpenSSH client was not found. Install it or add ssh to PATH')
        if identity and not Path(identity).is_file():
            raise ValueError('SSH Identity File does not exist')
        self.stop()
        # A second Blender must not silently connect to a different forward.
        with socket.socket() as probe:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                probe.bind(('127.0.0.1', local_port))
            except OSError as exc:
                raise RuntimeError(f'Local port {local_port} is in use. Close the previous tunnel or choose another Local Port') from exc
        self._errors = tempfile.TemporaryFile()
        try:
            self.process = subprocess.Popen(
                [executable, *arguments], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=self._errors, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
        except OSError:
            self._errors.close()
            self._errors = None
            raise
        self.status = 'Connecting'
        self._stop.clear()
        self._monitor = threading.Thread(target=self._watch, args=(local_port,), daemon=True)
        self._monitor.start()

    def _watch(self, local_port):
        while not self._stop.wait(.5):
            if self.process.poll() is not None:
                self._errors.seek(0)
                detail = self._errors.read(1800).decode('utf-8', errors='replace').strip()
                self.status = 'SSH exited: ' + (detail or str(self.process.returncode))
                return
            if self.status == 'Connecting':
                try:
                    with socket.create_connection(('127.0.0.1', local_port), timeout=.2):
                        self.status = f'Connected on 127.0.0.1:{local_port}'
                except OSError:
                    pass

    def stop(self):
        self._stop.set()
        if self._monitor is not None:
            self._monitor.join(timeout=2)
            self._monitor = None
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.process = None
        if self._errors is not None:
            self._errors.close()
            self._errors = None
        self.status = 'Disconnected'
