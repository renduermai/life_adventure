"""Bounded image decoding; never trust client MIME types or preserve EXIF."""
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 12_000_000
FORMATS = {'.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG', '.webp': 'WEBP'}


class MediaError(Exception):
    def __init__(self, code, message, status=422):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


@dataclass(frozen=True)
class SafeImage:
    data: bytes
    width: int
    height: int
    sha256: str
    content_type: str = 'image/webp'


def normalize_image(data: bytes, filename: str) -> SafeImage:
    if not data or len(data) > MAX_BYTES:
        raise MediaError('image_size', '图片不能为空，且不得超过5MB', 413)
    if not filename or len(filename) > 255 or '/' in filename or '\\' in filename or any(ord(c) < 32 for c in filename):
        raise MediaError('image_name', '图片文件名无效')
    expected = FORMATS.get(PurePosixPath(filename).suffix.lower())
    if not expected:
        raise MediaError('image_type', '仅支持JPG、PNG或WebP图片')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=list(set(FORMATS.values()))) as probe:
                if probe.format != expected or probe.width * probe.height > MAX_PIXELS:
                    raise MediaError('image_type', '图片真实格式不匹配，或像素超过1200万')
                if getattr(probe, 'n_frames', 1) != 1:
                    raise MediaError('image_animated', '请上传静态图片')
                probe.verify()
            with Image.open(BytesIO(data)) as source:
                source.load()
                oriented = ImageOps.exif_transpose(source)
                mode = 'RGBA' if 'A' in oriented.getbands() or 'transparency' in oriented.info else 'RGB'
                # A new image with pixels only drops EXIF/ICC/text and local metadata.
                clean = Image.new(mode, oriented.size)
                clean.paste(oriented.convert(mode))
                output = BytesIO()
                clean.save(output, format='WEBP', quality=85, method=4)
                encoded = output.getvalue()
                if len(encoded) > MAX_BYTES:
                    raise MediaError('image_size', '处理后的图片超过5MB', 413)
                return SafeImage(encoded, clean.width, clean.height, sha256(encoded).hexdigest())
    except MediaError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise MediaError('invalid_image', '图片损坏、格式无效或像素过大') from None
