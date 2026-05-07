from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from schools.models import School


class QueueMonitorAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Queue School", subdomain="queue-school")
        cls.admin = User.objects.create_user(
            username="queue_admin",
            password="pw12345",
            school=cls.school,
            role="school_admin",
        )
        cls.teacher = User.objects.create_user(
            username="queue_teacher",
            password="pw12345",
            school=cls.school,
            role="teacher",
        )

    def test_school_admin_can_open_queue_monitor(self):
        self.client.login(username="queue_admin", password="pw12345")
        resp = self.client.get(reverse("queue_monitor"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Queue Monitor")

    def test_non_leadership_user_is_blocked(self):
        self.client.login(username="queue_teacher", password="pw12345")
        resp = self.client.get(reverse("queue_monitor"))
        self.assertEqual(resp.status_code, 302)
