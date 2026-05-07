"""
Optional image compression and thumbnails for media uploads (Pillow).

Call from save handlers or views after upload — does not run automatically on every FileField.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


def compress_image_bytes(
    data: bytes,
    *,
    max_dim: int | None = None,
    jpeg_quality: int | None = None,
    output_format: str | None = None,
) -> tuple[bytes, str]:
    """Resize and re-encode image bytes. Returns (new_bytes, mime).

    If Pillow is unavailable or the file is not a raster image, returns (data, "").
    """
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return data, ""

    max_dim = max_dim or getattr(settings, "MEDIA_IMAGE_MAX_DIMENSION", 2400)
    jpeg_quality = jpeg_quality or getattr(settings, "MEDIA_JPEG_QUALITY", 85)

    try:
        im = Image.open(io.BytesIO(data))
        im = ImageOps.exif_transpose(im)
    except Exception:
        return data, ""

    fmt = (output_format or im.format or "JPEG").upper()
    if fmt not in ("JPEG", "JPG", "PNG", "WEBP"):
        fmt = "JPEG"

    w, h = im.size
    if max(w, h) > max_dim:
        ratio = max_dim / float(max(w, h))
        im = im.resize((int(w * ratio), int(h * ratio)), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    save_kw: dict = {"optimize": True}
    if fmt in ("JPEG", "JPG"):
        im = im.convert("RGB")
        save_kw["quality"] = max(40, min(95, int(jpeg_quality)))
        save_kw["progressive"] = True
        fmt = "JPEG"
    try:
        im.save(buf, format=fmt, **save_kw)
    except Exception:
        logger.debug("compress_image_bytes: save failed", exc_info=True)
        return data, ""
    out = buf.getvalue()
    if len(out) >= len(data):
        return data, ""
    mime = f"image/{fmt.lower()}" if fmt != "JPEG" else "image/jpeg"
    return out, mime


def make_thumbnail_bytes(data: bytes, *, max_size: int | None = None) -> bytes | None:
    """Return JPEG thumbnail bytes or None."""
    if not getattr(settings, "MEDIA_GENERATE_THUMBNAILS", False):
        return None
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return None
    max_size = max_size or getattr(settings, "MEDIA_THUMBNAIL_MAX", 400)
    try:
        im = Image.open(io.BytesIO(data))
        im = ImageOps.exif_transpose(im)
        im.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=82, optimize=True)
        return buf.getvalue()
    except Exception:
        return None


def thumbnail_relative_path(original_relative: str) -> str:
    """Derive sibling path ``name_thumb.jpg`` under the same directory."""
    p = Path(original_relative)
    return str(p.with_name(f"{p.stem}_thumb.jpg"))
