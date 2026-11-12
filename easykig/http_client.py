"""HTTP transport shared by main-thread operators and background mesh jobs.

This module never imports bpy. Blender data is only accessed by its UI thread.
"""
import json
import socket
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def normalize_url(base_url):
    parsed = urllib.parse.urlparse(base_url.strip().rstrip('/'))
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError('Server URL must be a valid http(s) URL')
    local = parsed.hostname in ('localhost', '127.0.0.1', '::1')
    if parsed.scheme != 'https' and not local:
        raise ValueError('Use HTTPS for remote servers, or tunnel to 127.0.0.1')
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Server URL must not contain credentials, queries or fragments')
    return base_url.strip().rstrip('/')


def http_bytes(url, timeout, headers, data=None, method=None, *, limit=33 * 1024 * 1024):
    request = urllib.request.Request(url, data=data, headers=headers,
                                    method=method or ('POST' if data is not None else 'GET'))
    try:
        handlers = [NoRedirect]
        if urllib.parse.urlparse(url).hostname in ('127.0.0.1', 'localhost', '::1'):
            handlers.append(urllib.request.ProxyHandler({}))
        opener = urllib.request.build_opener(*handlers)
        with opener.open(request, timeout=float(timeout)) as response:
            body = response.read(limit + 1)
            if len(body) > limit:
                raise RuntimeError('Server response exceeds the supported size')
            return body
    except urllib.error.HTTPError as exc:
        details = exc.read(1000).decode('utf-8', errors='replace')
        raise RuntimeError(f'HTTP {exc.code}: {details}') from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f'Cannot connect to server: {exc.reason}') from exc
    except socket.timeout as exc:
        raise RuntimeError('The server request timed out. Check the server or increase Request Timeout.') from exc
    except (ValueError, OSError) as exc:
        raise RuntimeError(f'Could not read the server response: {exc}') from exc


def http_json(url, timeout, headers, data=None, method=None):
    try:
        return json.loads(http_bytes(url, timeout, headers, data, method))
    except (ValueError, UnicodeError) as exc:
        raise RuntimeError('Server did not return valid JSON') from exc
