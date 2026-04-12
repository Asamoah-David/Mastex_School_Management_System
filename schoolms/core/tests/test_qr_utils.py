from django.test import SimpleTestCase, override_settings

from core.qr_utils import generate_student_qr_data, validate_qr_data


class _Student:
    def __init__(self, pk, admission_number):
        self.id = pk
        self.admission_number = admission_number


class QrUtilsTests(SimpleTestCase):
    def test_legacy_format_still_validates(self):
        r = validate_qr_data("MASEXTICKET:12:ADM-001")
        self.assertTrue(r["valid"])
        self.assertEqual(r["student_id"], 12)
        self.assertEqual(r["admission_number"], "ADM-001")
        self.assertTrue(r.get("legacy"))

    def test_v2_roundtrip(self):
        st = _Student(99, "GHS-2044")
        raw = generate_student_qr_data(st)
        self.assertTrue(raw.startswith("MASEXTICKET:v2:"))
        r = validate_qr_data(raw)
        self.assertTrue(r["valid"])
        self.assertEqual(r["student_id"], 99)
        self.assertEqual(r["admission_number"], "GHS-2044")
        self.assertNotIn("legacy", r)

    def test_empty_and_bad_prefix(self):
        self.assertFalse(validate_qr_data("")["valid"])
        self.assertFalse(validate_qr_data("OTHER:1:2")["valid"])

    def test_v2_tampered_fails(self):
        st = _Student(1, "A")
        raw = generate_student_qr_data(st)
        bad = raw[:-3] + "xxx"
        r = validate_qr_data(bad)
        self.assertFalse(r["valid"])

    @override_settings(SECRET_KEY="test-secret-key-for-qr-age")
    def test_v2_respects_max_age(self):
        st = _Student(5, "Z")
        raw = generate_student_qr_data(st)
        r = validate_qr_data(raw, max_age_seconds=86400 * 365)
        self.assertTrue(r["valid"])
        r2 = validate_qr_data(raw, max_age_seconds=0)
        self.assertFalse(r2["valid"])
