"""API v1 endpoints respect per-school SchoolFeature flags."""

import uuid

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from schools.models import School, SchoolFeature


class V1ResultsTimetableFeatureGateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="API Gate School", subdomain=f"api-gate-{uuid.uuid4().hex[:10]}"
        )
        cls.teacher = User.objects.create_user(
            username="api_gate_teacher",
            password="pw12345",
            school=cls.school,
            role="teacher",
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.teacher)

    def test_results_list_403_when_results_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="results", defaults={"enabled": False}
        )
        r = self.client.get(reverse("integrations:v1_results"))
        self.assertEqual(r.status_code, 403)
        self.assertIn("disabled", str(r.data.get("detail", "")).lower())

    def test_timetable_403_when_timetable_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="timetable", defaults={"enabled": False}
        )
        r = self.client.get(reverse("integrations:v1_timetable"))
        self.assertEqual(r.status_code, 403)
