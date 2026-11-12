"""Read and apply the display orientation recorded by cameras and image editors."""

import struct


def _tiff_orientation(data):
    if data.startswith(b'Exif\0\0'):
        data = data[6:]
    endian = {b'II': '<', b'MM': '>'}.get(data[:2])
    if endian is None:
        return None
    try:
        marker, offset = struct.unpack_from(endian + 'HI', data, 2)
        if marker != 42:
            return None
        count, = struct.unpack_from(endian + 'H', data, offset)
        for entry in range(count):
            at = offset + 2 + 12 * entry
            tag, kind, length = struct.unpack_from(endian + 'HHI', data, at)
            if tag == 274 and kind == 3 and length == 1:
                value, = struct.unpack_from(endian + 'H', data, at + 8)
                return value if 1 <= value <= 8 else None
    except struct.error:
        pass
    return None


def _jpeg_orientation(stream):
    stream.seek(2)
    while stream.read(1) == b'\xff':
        marker = stream.read(1)
        while marker == b'\xff':
            marker = stream.read(1)
        if marker in (b'', b'\xda', b'\xd9'):
            break
        length = stream.read(2)
        size = int.from_bytes(length, 'big') - 2
        if len(length) != 2 or size < 0:
            break
        if marker == b'\xe1':
            data = stream.read(size)
            if data.startswith(b'Exif\0\0'):
                return _tiff_orientation(data)
        else:
            stream.seek(size, 1)
    return None


def _chunk_orientation(stream, webp):
    stream.seek(12 if webp else 8)
    while len(header := stream.read(8)) == 8:
        if webp:
            tag, size = struct.unpack('<4sI', header)
            padding = size % 2
        else:
            size, tag = struct.unpack('>I4s', header)
            padding = 4  # PNG chunk CRC
            if tag == b'IEND':
                break
        if tag == (b'EXIF' if webp else b'eXIf') and size <= 256 * 1024:
            return _tiff_orientation(stream.read(size))
        stream.seek(size + padding, 1)
    return None


def image_orientation(path):
    with path.open('rb') as stream:
        header = stream.read(12)
        if header.startswith(b'\xff\xd8'):
            return _jpeg_orientation(stream) or 1
        if header.startswith(b'\x89PNG\r\n\x1a\n'):
            return _chunk_orientation(stream, webp=False) or 1
        if header.startswith(b'RIFF') and header[8:12] == b'WEBP':
            return _chunk_orientation(stream, webp=True) or 1
    return 1


def orient_pixels(pixels, orientation):
    """Transform Blender's bottom-up pixel rows to the image's display orientation."""
    import numpy as np

    rows = pixels[::-1]
    transforms = {
        2: lambda a: a[:, ::-1],
        3: lambda a: a[::-1, ::-1],
        4: lambda a: a[::-1],
        5: lambda a: a.swapaxes(0, 1),
        6: lambda a: np.rot90(a, 3),
        7: lambda a: a.swapaxes(0, 1)[::-1, ::-1],
        8: lambda a: np.rot90(a),
    }
    return transforms[orientation](rows)[::-1] if orientation in transforms else pixels
