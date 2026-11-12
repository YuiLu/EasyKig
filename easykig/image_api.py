"""OpenAI-compatible image API requests made directly from Blender."""

import base64
import uuid

from .remote import _normalize_url, http_json


def _request(prefs, path, headers=None, body=None):
    base = _normalize_url(prefs.image_api_base)
    request_headers = {'Accept': 'application/json', **(headers or {})}
    key = prefs.image_api_key.strip()
    if key:
        request_headers['Authorization'] = f'Bearer {key}'
    return http_json(base + path, prefs.timeout_seconds, request_headers, body)


def list_models(prefs):
    response = _request(prefs, '/models')
    try:
        entries = response['data']
        models = sorted({entry['id'] for entry in entries if entry['id']})
        if not all(isinstance(model, str) for model in models):
            raise TypeError
        return models
    except (KeyError, TypeError) as exc:
        raise ValueError('Image API /models did not return a compatible model list') from exc


def edit_image(prefs, model, prompt, images):
    if not model:
        raise ValueError('Choose an Image Model in EasyKig preferences')
    boundary = uuid.uuid4().hex
    body = bytearray()
    for name, value in {'model': model, 'prompt': prompt, 'size': '1024x1024'}.items():
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(value.encode('utf-8') + b'\r\n')
    field = 'image' if len(images) == 1 else 'image[]'
    for index, image in enumerate(images, 1):
        body.extend(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; '
            f'filename="reference_{index}.png"\r\nContent-Type: image/png\r\n\r\n'.encode()
        )
        body.extend(base64.b64decode(image, validate=True) + b'\r\n')
    body.extend(f'--{boundary}--\r\n'.encode())
    result = _request(prefs, '/images/edits', {'Content-Type': f'multipart/form-data; boundary={boundary}'}, bytes(body))
    try:
        image = result['data'][0]['b64_json']
        if not isinstance(image, str) or not image:
            raise ValueError
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValueError('Image API did not return a base64 PNG from /images/edits') from exc
    return {'image_png_base64': image}
