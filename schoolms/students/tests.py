"""Leaver clearance and related student workflow tests."""

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from schools.models import School
from students.models import Student, StudentClearance


class StudentClearanceExitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Clearance Test Sch", subdomain="clr-tst-sch-01")
        cls.librarian = User.objects.create_user(
            username="clr_lib", password="pw12345", school=cls.school, role="librarian"
        )
        cls.head = User.objects.create_user(
            username="clr_head", password="pw12345", school=cls.school, role="school_admin"
        )
        su = User.objects.create_user(
            username="clr_stu", password="pw12345", school=cls.school, role="student"
        )
        cls.student = Student.objects.create(
            school=cls.school, user=su, admission_number="CLR01", class_name="1A"
        )

    def setUp(self):
        self.client = Client()

    def test_exit_redirects_when_clearance_incomplete(self):
        StudentClearance.objects.create(
            student=self.student,
            fees_cleared=False,
            library_cleared=False,
            discipline_cleared=False,
            id_card_returned=False,
        )
        self.client.login(username="clr_lib", password="pw12345")
        r = self.client.post(
            reverse("students:student_exit", args=[self.student.pk]),
            {"exit_reason": "left", "exit_notes": ""},
        )
        self.assertEqual(r.status_code, 302)
        self.assertIn("clearance", r.url)
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, "active")

    def test_exit_succeeds_when_clearance_complete(self):
        StudentClearance.objects.create(
            student=self.student,
            fees_cleared=True,
            library_cleared=True,
            discipline_cleared=True,
            id_card_returned=True,
        )
        self.client.login(username="clr_lib", password="pw12345")
        r = self.client.post(
            reverse("students:student_exit", args=[self.student.pk]),
            {"exit_reason": "left", "exit_notes": ""},
        )
        self.assertEqual(r.status_code, 302)
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, "withdrawn")

    def test_leadership_override_skips_clearance(self):
        StudentClearance.objects.create(
            student=self.student,
            fees_cleared=False,
            library_cleared=False,
            discipline_cleared=False,
            id_card_returned=False,
        )
        self.client.login(username="clr_head", password="pw12345")
        r = self.client.post(
            reverse("students:student_exit", args=[self.student.pk]),
            {
                "exit_reason": "transferred",
                "exit_notes": "",
                "clearance_override": "on",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, "withdrawn")
