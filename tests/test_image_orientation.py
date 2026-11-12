import struct

import pytest

from easykig.image_orientation import image_orientation


@pytest.mark.parametrize('endian,byte_order', [('<', b'II'), ('>', b'MM')])
def test_camera_orientation_for_jpeg_png_and_webp(tmp_path, endian, byte_order):
    tiff = byte_order + struct.pack(endian + 'HIHHHIH', 42, 8, 1, 274, 3, 1, 6) + b'\0' * 6
    exif = b'Exif\0\0' + tiff
    webp_chunk = b'EXIF' + struct.pack('<I', len(exif)) + exif
    images = {
        'jpg': b'\xff\xd8\xff\xe1' + struct.pack('>H', len(exif) + 2) + exif,
        'png': b'\x89PNG\r\n\x1a\n' + struct.pack('>I', len(tiff)) + b'eXIf' + tiff + b'\0' * 4,
        'webp': b'RIFF' + struct.pack('<I', len(webp_chunk) + 4) + b'WEBP' + webp_chunk,
    }
    for suffix, image in images.items():
        path = tmp_path / f'portrait.{suffix}'
        path.write_bytes(image)
        assert image_orientation(path) == 6


def test_malformed_exif_keeps_pixel_orientation(tmp_path):
    path = tmp_path / 'portrait.jpg'
    path.write_bytes(b'\xff\xd8\xff\xe1\0\x0aExif\0\0II')
    assert image_orientation(path) == 1
