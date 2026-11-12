"""Source-resolution image previews with a bounded cache."""

from collections import OrderedDict
from pathlib import Path

import bpy
import bpy.utils.previews

from .image_orientation import image_orientation, orient_pixels


_PREVIEW_EDGE = 1024
_CACHE_SIZE = 12
_previews = None
_files = OrderedDict()
_pending = OrderedDict()


def _upgrade_one():
    import numpy as np

    key, signature = _pending.popitem(last=False)
    image = None
    try:
        path, _ = signature
        if _files.get(key) == signature and key in _previews:
            image = bpy.data.images.load(str(path), check_existing=False)
            width, height = image.size
            if not width or not height:
                return .02 if _pending else None
            scale = min(1, _PREVIEW_EDGE / max(width, height))
            if scale < 1:
                image.scale(max(1, round(width * scale)), max(1, round(height * scale)))
                width, height = image.size

            pixels = np.empty(width * height * 4, dtype=np.float32)
            image.pixels.foreach_get(pixels)
            rgba = orient_pixels(pixels.reshape(height, width, 4), image_orientation(path))
            rgba = np.ascontiguousarray(np.rint(np.clip(rgba, 0, 1) * 255).astype(np.uint8))
            preview = _previews[key]
            preview.image_size = (rgba.shape[1], rgba.shape[0])
            preview.image_pixels = rgba.view(np.int32).ravel().tolist()
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()
    except (OSError, RuntimeError, ValueError):
        pass  # Keep the thumbnail if a full-size decode fails.
    finally:
        if image is not None:
            bpy.data.images.remove(image)
    return .02 if _pending else None


def preview_icon(filename):
    if not filename:
        return 0
    path = Path(bpy.path.abspath(filename))
    key = str(path)
    try:
        signature = (path, path.stat().st_mtime_ns)
    except OSError:
        return 0
    if _files.get(key) != signature:
        if key in _previews:
            del _previews[key]
        _files[key] = signature
        try:
            preview = _previews.load(key, str(path), 'IMAGE', force_reload=True)
            orientation = image_orientation(path)
            if orientation != 1 and all(preview.image_size):
                import numpy as np

                width, height = preview.image_size
                pixels = np.asarray(preview.image_pixels, dtype=np.int32).reshape(height, width)
                pixels = orient_pixels(pixels, orientation)
                preview.image_size = (pixels.shape[1], pixels.shape[0])
                preview.image_pixels = pixels.ravel().tolist()
            _pending[key] = signature
            if not bpy.app.timers.is_registered(_upgrade_one):
                bpy.app.timers.register(_upgrade_one, first_interval=.01)
        except (OSError, RuntimeError, ValueError):
            if key in _previews:
                del _previews[key]
    _files.move_to_end(key)
    if len(_files) > _CACHE_SIZE:
        old, _ = _files.popitem(last=False)
        _pending.pop(old, None)
        if old in _previews:
            del _previews[old]
    return _previews[key].icon_id if key in _previews else 0


def _preview_items(filename):
    icon = preview_icon(filename)
    return [('IMAGE', 'Image Preview', 'Click to enlarge', icon, 0)] if icon else []


def reference_preview_items(settings, _context):
    return _preview_items(settings.reference_image)


def extra_preview_items(item, _context):
    return _preview_items(item.path)


def result_preview_items(settings, _context):
    return _preview_items(getattr(settings, f'last_{settings.result_view}_png'))


def register():
    global _previews
    _previews = bpy.utils.previews.new()


def unregister():
    global _previews
    if bpy.app.timers.is_registered(_upgrade_one):
        bpy.app.timers.unregister(_upgrade_one)
    bpy.utils.previews.remove(_previews)
    _previews = None
    _files.clear()
    _pending.clear()
