"""Auto timetable: staff-only + timetable feature (non-superuser)."""

import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from schools.models import School, SchoolFeature
from students.models import Student

User = get_user_model()


class AutoTimetableAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="AutoTT Sch", subdomain=f"autott-{uuid.uuid4().hex[:8]}")
        cls.student = User.objects.create_user(
            username="autott_student", password="pw12345", school=cls.school, role="student"
        )
        Student.objects.create(
            school=cls.school,
            user=cls.student,
            admission_number="ATT-01",
            class_name="1Z",
            status="active",
        )
        cls.admin = User.objects.create_user(
            username="autott_admin", password="pw12345", school=cls.school, role="school_admin"
        )
        SchoolFeature.objects.update_or_create(
            school=cls.school, key="timetable", defaults={"enabled": True}
        )

    def setUp(self):
        self.client = Client()

    def test_student_cannot_open_auto_timetable(self):
        self.client.login(username="autott_student", password="pw12345")
        r = self.client.get(reverse("academics:auto_timetable"))
        self.assertEqual(r.status_code, 302)

    def test_admin_post_renders_preview(self):
        self.client.login(username="autott_admin", password="pw12345")
        url = reverse("academics:auto_timetable")
        r = self.client.post(url, {"class_name": "1Z"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Draft preview")
