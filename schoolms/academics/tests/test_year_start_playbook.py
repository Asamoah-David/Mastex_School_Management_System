from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from schools.models import School, SchoolFeature


class YearStartPlaybookTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Playbook School", subdomain="pb-sch-01")
        for key in ("results", "exams", "timetable"):
            SchoolFeature.objects.update_or_create(
                school=cls.school, key=key, defaults={"enabled": True}
            )
        cls.admin = User.objects.create_user(
            username="pb_admin",
            password="pw12345",
            school=cls.school,
            role="school_admin",
        )
        cls.teacher = User.objects.create_user(
            username="pb_teacher",
            password="pw12345",
            school=cls.school,
            role="teacher",
        )

    def setUp(self):
        self.client = Client()

    def test_anonymous_redirects(self):
        r = self.client.get(reverse("academics:year_start_playbook"))
        self.assertEqual(r.status_code, 302)

    def test_teacher_can_view_when_features_enabled(self):
        """Staff with school + term-related features see the playbook (same gate as term_list)."""
        self.client.login(username="pb_teacher", password="pw12345")
        r = self.client.get(reverse("academics:year_start_playbook"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "New academic year")

    def test_school_admin_sees_playbook(self):
        self.client.login(username="pb_admin", password="pw12345")
        r = self.client.get(reverse("academics:year_start_playbook"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "New academic year")
