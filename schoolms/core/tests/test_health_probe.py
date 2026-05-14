"""HTTP health / readiness probes (schoolms.urls)."""

from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse


class HealthProbeTests(TestCase):
    def test_health_returns_200_when_ok(self):
        r = Client().get(reverse("health_check"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("status"), "ok")

    @override_settings(HEALTH_HTTP_STRICT=True)
    @patch("schoolms.urls.connection.ensure_connection", side_effect=RuntimeError("db down"))
    def test_health_strict_returns_503_when_db_unavailable(self, _mock):
        r = Client().get(reverse("health_check"))
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json().get("status"), "degraded")

    def test_ready_returns_503_when_db_unavailable(self):
        with patch("schoolms.urls.connection.ensure_connection", side_effect=RuntimeError("db down")):
            r = Client().get(reverse("ready_check"))
        self.assertEqual(r.status_code, 503)
