"""Tests for upload validation helpers."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from core.upload_validation import InvalidUploadError, validate_image_upload


class UploadValidationTests(SimpleTestCase):
    def test_rejects_bad_extension(self):
        f = SimpleUploadedFile("doc.exe", b"not an image", content_type="application/octet-stream")
        with self.assertRaisesMessage(
            InvalidUploadError, "supported image type"
        ):
            validate_image_upload(f, verify_image=False)

    @override_settings(OMR_MAX_UPLOAD_BYTES=100)
    def test_rejects_oversize_without_pillow_verify(self):
        f = SimpleUploadedFile("x.jpg", b"x" * 200, content_type="image/jpeg")
        with self.assertRaisesMessage(InvalidUploadError, "too large"):
            validate_image_upload(f, verify_image=False)

    def test_accepts_small_file_when_verify_skipped(self):
        f = SimpleUploadedFile("x.jpg", b"fake", content_type="image/jpeg")
        validate_image_upload(f, verify_image=False)
