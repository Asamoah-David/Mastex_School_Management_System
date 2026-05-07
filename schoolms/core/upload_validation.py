"""
Validate uploaded files (size, extension, basic image integrity).
Used by OMR and other upload flows to reject obviously unsafe inputs early.
"""

from __future__ import annotations

import os

from django.conf import settings

# Reasonable default for sheet photos; override with OMR_MAX_UPLOAD_BYTES in settings.
_DEFAULT_MAX_BYTES = 10 * 1024 * 1024

_ALLOWED_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"})


class InvalidUploadError(Exception):
    """User-facing upload rejection (message is safe to show in UI)."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def max_upload_bytes() -> int:
    return int(
        getattr(settings, "OMR_MAX_UPLOAD_BYTES", None)
        or getattr(settings, "DATA_UPLOAD_MAX_MEMORY_SIZE", None)
        or _DEFAULT_MAX_BYTES
    )


def validate_image_upload(
    uploaded_file,
    *,
    max_bytes: int | None = None,
    verify_image: bool = True,
) -> None:
    """
    Raise InvalidUploadError if the file should not be processed.

    - Enforces size limit
    - Enforces extension whitelist (client-supplied names are not trusted for MIME)
    - Optionally opens with Pillow to catch truncated/corrupt images
    """
    if uploaded_file is None:
        raise InvalidUploadError("No file was uploaded.")

    limit = max_bytes if max_bytes is not None else max_upload_bytes()
    name = getattr(uploaded_file, "name", "") or "upload"
    ext = os.path.splitext(name)[1].lower()
    if ext not in _ALLOWED_IMAGE_EXTENSIONS:
        raise InvalidUploadError(
            "Please upload a supported image type (JPEG, PNG, WebP, BMP, or TIFF)."
        )

    size = getattr(uploaded_file, "size", None)
    if size is not None and size > limit:
        mb = limit // (1024 * 1024)
        raise InvalidUploadError(f"Image is too large (maximum about {mb} MB). Try compressing the photo.")

    if verify_image:
        uploaded_file.seek(0)
        try:
            from PIL import Image
            from PIL import UnidentifiedImageError
        except ImportError:
            uploaded_file.seek(0)
            return
        try:
            with Image.open(uploaded_file) as im:
                im.verify()
        except UnidentifiedImageError as exc:
            raise InvalidUploadError("The file does not look like a valid image.") from exc
        except Exception as exc:
            raise InvalidUploadError("Could not read the image file. Try another photo or format.") from exc
        uploaded_file.seek(0)
