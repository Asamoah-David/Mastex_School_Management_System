"""Feature gates for homework, quiz, exams, timetable, terms, report cards, and related flows."""

import uuid

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from schools.models import School, SchoolFeature


class HomeworkQuizFeatureGateTests(TestCase):
    """Homework and quiz views respect SchoolFeature flags."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Acad Gate School", subdomain=f"acad-gate-{uuid.uuid4().hex[:10]}"
        )
        cls.teacher = User.objects.create_user(
            username="acad_gate_teacher", password="pw12345", school=cls.school, role="teacher"
        )

    def setUp(self):
        self.client = Client()

    def test_homework_list_redirects_when_homework_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="homework", defaults={"enabled": False}
        )
        self.client.login(username="acad_gate_teacher", password="pw12345")
        r = self.client.get(reverse("academics:homework_list"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)

    def test_quiz_list_redirects_when_quiz_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="quiz", defaults={"enabled": False}
        )
        self.client.login(username="acad_gate_teacher", password="pw12345")
        r = self.client.get(reverse("academics:quiz_list"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)

    def test_result_import_upload_redirects_when_results_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="results", defaults={"enabled": False}
        )
        self.client.login(username="acad_gate_teacher", password="pw12345")
        r = self.client.get(reverse("academics:result_import_upload"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)

    def test_question_bank_list_redirects_when_question_bank_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="question_bank", defaults={"enabled": False}
        )
        self.client.login(username="acad_gate_teacher", password="pw12345")
        r = self.client.get(reverse("academics:question_bank_list"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)

    def test_exam_schedule_list_redirects_when_exams_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="exams", defaults={"enabled": False}
        )
        self.client.login(username="acad_gate_teacher", password="pw12345")
        r = self.client.get(reverse("academics:exam_schedule_list"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)

    def test_timetable_list_redirects_when_timetable_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="timetable", defaults={"enabled": False}
        )
        self.client.login(username="acad_gate_teacher", password="pw12345")
        r = self.client.get(reverse("academics:timetable_list"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)


class ReportCardFeatureGateTests(TestCase):
    """Report card staff workflow respects ``report_cards`` flag."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="RC Gate School", subdomain=f"rc-gate-{uuid.uuid4().hex[:10]}"
        )
        cls.admin = User.objects.create_user(
            username="rc_gate_admin", password="pw12345", school=cls.school, role="school_admin"
        )

    def setUp(self):
        self.client = Client()

    def test_report_card_generator_redirects_when_report_cards_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="report_cards", defaults={"enabled": False}
        )
        self.client.login(username="rc_gate_admin", password="pw12345")
        r = self.client.get(reverse("academics:report_card_generator"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)


class TermManagementAnyFeatureGateTests(TestCase):
    """Term CRUD requires at least one of results, exams, or timetable."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Term Gate School", subdomain=f"term-gate-{uuid.uuid4().hex[:10]}"
        )
        cls.admin = User.objects.create_user(
            username="term_gate_admin", password="pw12345", school=cls.school, role="school_admin"
        )

    def setUp(self):
        self.client = Client()

    def test_term_list_redirects_when_results_exams_timetable_all_disabled(self):
        for key in ("results", "exams", "timetable"):
            SchoolFeature.objects.update_or_create(
                school=self.school, key=key, defaults={"enabled": False}
            )
        self.client.login(username="term_gate_admin", password="pw12345")
        r = self.client.get(reverse("academics:term_list"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)
