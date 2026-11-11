"""Small synchronous HTTP adapter for explicit user-triggered Blender operators.

Blender operator calls are blocking in this MVP; do not invoke from draw(), timers or handlers.
"""
import base64
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
import bpy


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _normalize_url(base_url):
    parsed = urllib.parse.urlparse(base_url.strip().rstrip("/"))
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Server URL must be a valid http(s) URL")
    # On a remote host require transport encryption. Local SSH port forwarding remains supported.
    local = parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if parsed.scheme != "https" and not local:
        raise ValueError("Use HTTPS for remote servers, or tunnel to 127.0.0.1")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Server URL must not contain credentials, queries or fragments")
    return base_url.strip().rstrip("/")


def request_json(prefs, path, payload=None, method=None):
    if not bpy.app.online_access:
        raise RuntimeError("Enable Allow Online Access in Blender Preferences to use the server")
    url = _normalize_url(prefs.server_url) + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if prefs.server_token and data is not None:
        headers["Authorization"] = "Bearer " + prefs.server_token
    request = urllib.request.Request(url, data=data, headers=headers, method=method or ("POST" if data is not None else "GET"))
    try:
        opener = urllib.request.build_opener(NoRedirect)
        with opener.open(request, timeout=float(prefs.timeout_seconds)) as response:
            limit = 33 * 1024 * 1024
            body = response.read(limit + 1)
            if len(body) > limit:
                raise RuntimeError("Server response exceeds the supported size")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        details = exc.read(1000).decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {details}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot connect to server: {exc.reason}") from exc
    except socket.timeout as exc:
        raise RuntimeError("The server request timed out. Check the server or increase Request Timeout.") from exc
    except (ValueError, OSError) as exc:
        raise RuntimeError(f"Could not read the server response: {exc}") from exc


def encode_png(filepath):
    raw = Path(filepath).read_bytes()
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Expected a PNG image")
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("Image exceeds 8 MB; lower render resolution")
    return base64.b64encode(raw).decode("ascii")


def save_b64_png(content, filepath):
    raw = base64.b64decode(content, validate=True)
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Preview server did not return PNG")
    if len(raw) > 24 * 1024 * 1024:
        raise ValueError("Preview image exceeds maximum size")
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    Path(filepath).write_bytes(raw)
    return filepath
