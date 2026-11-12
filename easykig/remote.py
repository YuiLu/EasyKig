"""Image and parameter request helpers for explicit Blender operators.

Long 3D jobs use the bpy-free background client in mesh_jobs instead.
"""
import base64
import json
import tempfile
from pathlib import Path
import bpy

from .image_orientation import image_orientation, orient_pixels

REFERENCE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp')
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


from .http_client import NoRedirect, normalize_url as _normalize_url, http_json as _http_json


def request_json(prefs, path, payload=None, method=None, *, authenticated=False):
    url = _normalize_url(prefs.server_url) + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if prefs.server_token and (data is not None or authenticated):
        headers["Authorization"] = "Bearer " + prefs.server_token
    return http_json(url, prefs.timeout_seconds, headers, data, method)


def http_json(url, timeout, headers, data=None, method=None):
    if not bpy.app.online_access:
        raise RuntimeError("Enable Allow Online Access in Blender Preferences to use the server")
    return _http_json(url, timeout, headers, data, method)


def validate_reference_image(filepath):
    path = Path(filepath)
    suffix = path.suffix.lower()
    if suffix not in REFERENCE_EXTENSIONS:
        raise ValueError('Choose a PNG, JPEG or WebP image')
    with path.open('rb') as stream:
        header = stream.read(12)
    if suffix == '.png':
        valid = header.startswith(PNG_SIGNATURE)
    elif suffix in ('.jpg', '.jpeg'):
        valid = header.startswith(b'\xff\xd8\xff')
    else:
        valid = header.startswith(b'RIFF') and header[8:12] == b'WEBP'
    if not valid:
        raise ValueError('The file does not match its image format')
    return path


def _read_png(path):
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("Image exceeds 8 MB as PNG. Resize it before generating.")
    return path.read_bytes()


def encode_png(filepath):
    path = validate_reference_image(filepath)
    orientation = image_orientation(path)
    if path.suffix.lower() == '.png' and orientation == 1:
        return base64.b64encode(_read_png(path)).decode('ascii')

    image = bpy.data.images.load(str(path), check_existing=False)
    rotated = None
    try:
        if not image.size[0]:
            raise ValueError('Blender could not decode the reference image')
        if orientation != 1:
            import numpy as np

            width, height = image.size
            pixels = np.empty(width * height * 4, dtype=np.float32)
            image.pixels.foreach_get(pixels)
            pixels = orient_pixels(pixels.reshape(height, width, 4), orientation)
            height, width = pixels.shape[:2]
            rotated = bpy.data.images.new('EasyKig Oriented Reference', width, height, alpha=True)
            rotated.colorspace_settings.name = image.colorspace_settings.name
            rotated.pixels.foreach_set(np.ascontiguousarray(pixels).ravel())
        with tempfile.TemporaryDirectory(prefix='easykig-image-') as directory:
            converted = Path(directory) / 'reference.png'
            output = rotated or image
            output.file_format = 'PNG'
            output.save(filepath=str(converted))
            raw = _read_png(converted)
    finally:
        if rotated is not None:
            bpy.data.images.remove(rotated)
        bpy.data.images.remove(image)
    return base64.b64encode(raw).decode("ascii")


def save_b64_png(content, filepath):
    raw = base64.b64decode(content, validate=True)
    if not raw.startswith(PNG_SIGNATURE):
        raise ValueError("Preview server did not return PNG")
    if len(raw) > 24 * 1024 * 1024:
        raise ValueError("Preview image exceeds maximum size")
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    Path(filepath).write_bytes(raw)
    return filepath
