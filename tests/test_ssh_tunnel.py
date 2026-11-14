import socket
import sys
import time

import pytest

from easykig.ssh_tunnel import SshTunnel, ssh_arguments


def test_ssh_config_alias_and_key_are_passed_as_arguments():
    arguments = ssh_arguments('my-container', 0, '', '', 8001, '127.0.0.1', 8001)
    assert arguments[-3:] == ['-L', '127.0.0.1:8001:127.0.0.1:8001', 'my-container']
    assert '-p' not in arguments and '-l' not in arguments
    arguments = ssh_arguments('magic-lab.tech', 35995, 'root', 'C:/my keys/key', 8002, '::1', 8001)
    assert arguments[arguments.index('-i') + 1] == 'C:/my keys/key'
    assert '127.0.0.1:8002:[::1]:8001' in arguments
    assert 'BatchMode=yes' in arguments
    assert not any('StrictHostKeyChecking=no' in value for value in arguments)


@pytest.mark.parametrize('host', ['', '-oProxyCommand=bad', 'bad\nhost'])
def test_invalid_ssh_host_is_rejected(host):
    with pytest.raises(ValueError):
        ssh_arguments(host, 0, '', '', 8001, '127.0.0.1', 8001)


def test_port_conflict_does_not_launch_or_stop_an_existing_service(monkeypatch):
    from easykig import ssh_tunnel

    monkeypatch.setattr(ssh_tunnel.shutil, 'which', lambda _: sys.executable)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        tunnel = SshTunnel()
        with pytest.raises(RuntimeError, match='in use'):
            tunnel.start(host='test-container', local_port=listener.getsockname()[1])
        assert tunnel.process is None


def test_owned_process_is_hidden_and_closed(monkeypatch):
    from easykig import ssh_tunnel

    real_popen = ssh_tunnel.subprocess.Popen
    calls = []
    def launch(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return real_popen([sys.executable, '-c', 'import time; time.sleep(30)'], **kwargs)

    monkeypatch.setattr(ssh_tunnel.shutil, 'which', lambda _: sys.executable)
    monkeypatch.setattr(ssh_tunnel.subprocess, 'Popen', launch)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    tunnel = SshTunnel()
    try:
        tunnel.start(host='test-container', local_port=port)
        owned = tunnel.process
        assert owned.poll() is None
        assert calls[0][1]['creationflags'] == getattr(ssh_tunnel.subprocess, 'CREATE_NO_WINDOW', 0)
    finally:
        tunnel.stop()
    assert owned.poll() is not None
    assert tunnel.status == 'Disconnected'


def test_ssh_authentication_failure_reaches_status(monkeypatch):
    from easykig import ssh_tunnel

    real_popen = ssh_tunnel.subprocess.Popen
    monkeypatch.setattr(ssh_tunnel.shutil, 'which', lambda _: sys.executable)
    monkeypatch.setattr(ssh_tunnel.subprocess, 'Popen', lambda arguments, **kwargs: real_popen(
        [sys.executable, '-c', 'import sys; sys.stderr.write("Permission denied"); sys.exit(255)'], **kwargs))
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    tunnel = SshTunnel()
    try:
        tunnel.start(host='test-container', local_port=port)
        deadline = time.monotonic() + 3
        while tunnel.status == 'Connecting' and time.monotonic() < deadline:
            time.sleep(.05)
        assert 'Permission denied' in tunnel.status
    finally:
        tunnel.stop()
