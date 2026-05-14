"""Tests for ``core.phone_utils``."""

from django.test import SimpleTestCase

from core.phone_utils import normalize_phone_for_sms, phone_search_q, digits_only


class PhoneUtilsTests(SimpleTestCase):
    def test_normalize_ghana_local(self):
        self.assertEqual(normalize_phone_for_sms("0241 234 567"), "233241234567")

    def test_normalize_keeps_country_code(self):
        self.assertEqual(normalize_phone_for_sms("+233 24 412 3456"), "233244123456")

    def test_digits_only(self):
        self.assertEqual(digits_only("(024) 123-4567"), "0241234567")

    def test_phone_search_q_builds_variants(self):
        q = phone_search_q("phone", "+233 24 400 0000")
        self.assertTrue(q)
