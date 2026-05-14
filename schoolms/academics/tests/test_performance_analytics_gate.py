"""Performance analytics dashboard respects SchoolFeature('performance_analytics')."""

import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from schools.models import School, SchoolFeature

User = get_user_model()


class PerformanceAnalyticsFeatureGateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Perf Ana School", subdomain=f"perf-ana-{uuid.uuid4().hex[:8]}")
        SchoolFeature.objects.update_or_create(
            school=cls.school, key="performance_analytics", defaults={"enabled": True}
        )
        cls.admin = User.objects.create_user(
            username="perf_ana_admin", password="pw12345", school=cls.school, role="school_admin"
        )

    def setUp(self):
        self.client = Client()
        SchoolFeature.objects.update_or_create(
            school=self.school, key="performance_analytics", defaults={"enabled": True}
        )

    def test_redirect_when_feature_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="performance_analytics", defaults={"enabled": False}
        )
        self.client.login(username="perf_ana_admin", password="pw12345")
        r = self.client.get(reverse("academics:performance_analytics"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)

    def test_renders_when_enabled(self):
        self.client.login(username="perf_ana_admin", password="pw12345")
        r = self.client.get(reverse("academics:performance_analytics"))
        self.assertEqual(r.status_code, 200)
