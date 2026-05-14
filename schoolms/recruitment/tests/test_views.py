"""Recruitment school-admin flows: status actions, scoping, feature gate."""
from datetime import time, timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from recruitment.models import InterviewSchedule, JobApplication, JobPosting
from schools.models import School, SchoolFeature


class RecruitmentSchoolApplicationActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school_a = School.objects.create(name="Recruit School A", subdomain="recruit-sch-a")
        cls.school_b = School.objects.create(name="Recruit School B", subdomain="recruit-sch-b")
        User.objects.create_user(
            username="recruit_admin_a", password="pw", school=cls.school_a, role="school_admin"
        )
        deadline = timezone.now().date() + timedelta(days=14)
        cls.job_a = JobPosting.objects.create(
            school=cls.school_a,
            title="Math Teacher",
            description="Teach math",
            requirements="Degree",
            deadline=deadline,
        )
        cls.job_b = JobPosting.objects.create(
            school=cls.school_b,
            title="English Teacher",
            description="Teach english",
            requirements="Degree",
            deadline=deadline,
        )

    def setUp(self):
        cache.clear()
        self.app_a = JobApplication.objects.create(
            job=self.job_a,
            full_name="Applicant One",
            email="one@test.example",
            phone="+233200000001",
            cover_letter="Hire me",
            payment_status="paid",
            status="submitted",
            amount_paid=50,
        )

    def test_application_action_shortlist_allowed(self):
        self.client.login(username="recruit_admin_a", password="pw")
        url = reverse("recruitment:school_application_action", kwargs={"pk": self.app_a.pk})
        with patch("recruitment.views._send_email"), patch("recruitment.views._send_sms_notice"):
            r = self.client.post(url, {"status": "shortlisted"}, follow=True)
        self.assertEqual(r.status_code, 200)
        self.app_a.refresh_from_db()
        self.assertEqual(self.app_a.status, "shortlisted")

    def test_application_action_submitted_not_allowed(self):
        self.client.login(username="recruit_admin_a", password="pw")
        url = reverse("recruitment:school_application_action", kwargs={"pk": self.app_a.pk})
        self.client.post(url, {"status": "submitted"}, follow=True)
        self.app_a.refresh_from_db()
        self.assertEqual(self.app_a.status, "submitted")

    def test_application_action_cross_school_returns_404(self):
        app_b = JobApplication.objects.create(
            job=self.job_b,
            full_name="Other",
            email="other@test.example",
            phone="+233200000002",
            cover_letter="Text",
            payment_status="paid",
            status="submitted",
        )
        self.client.login(username="recruit_admin_a", password="pw")
        url = reverse("recruitment:school_application_action", kwargs={"pk": app_b.pk})
        r = self.client.post(url, {"status": "shortlisted"})
        self.assertEqual(r.status_code, 404)

    def test_job_portal_disabled_redirects_before_action(self):
        SchoolFeature.objects.create(school=self.school_a, key="job_portal", enabled=False)
        cache.clear()
        self.client.login(username="recruit_admin_a", password="pw")
        url = reverse("recruitment:school_application_action", kwargs={"pk": self.app_a.pk})
        r = self.client.post(url, {"status": "shortlisted"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("accounts:school_dashboard"))
        self.app_a.refresh_from_db()
        self.assertEqual(self.app_a.status, "submitted")


class JobApplicationScheduledInterviewAccessorTests(TestCase):
    """``scheduled_interview`` must not raise when the reverse OneToOne row is absent."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="SI School", subdomain="si-school-x")
        cls.job = JobPosting.objects.create(
            school=cls.school,
            title="Role",
            description="Desc",
            requirements="Req",
            deadline=timezone.now().date() + timedelta(days=7),
        )

    def test_scheduled_interview_none_without_row(self):
        app = JobApplication.objects.create(
            job=self.job,
            full_name="Applicant",
            email="si-none@example.com",
            phone="+233200000099",
            cover_letter="Letter",
            payment_status="paid",
            status="submitted",
        )
        self.assertIsNone(app.scheduled_interview)

    def test_scheduled_interview_returns_row_when_present(self):
        app = JobApplication.objects.create(
            job=self.job,
            full_name="Interviewee",
            email="si-row@example.com",
            phone="+233200000088",
            cover_letter="Letter",
            payment_status="paid",
            status="interview_scheduled",
        )
        InterviewSchedule.objects.create(
            application=app,
            interview_date=timezone.now().date() + timedelta(days=3),
            interview_time=time(10, 30),
        )
        self.assertIsNotNone(app.scheduled_interview)
        self.assertEqual(app.scheduled_interview.interview_time.hour, 10)


class RecruitmentSchoolApplicationDetailTests(TestCase):
    """Status form on application detail matches staff action whitelist."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Detail School", subdomain="detail-sch-x")
        User.objects.create_user(
            username="detail_admin", password="pw", school=cls.school, role="school_admin"
        )
        deadline = timezone.now().date() + timedelta(days=14)
        cls.job = JobPosting.objects.create(
            school=cls.school,
            title="Science Teacher",
            description="Teach",
            requirements="Degree",
            deadline=deadline,
        )

    def setUp(self):
        cache.clear()

    def test_detail_dropdown_submitted_shows_placeholder_no_submitted_value(self):
        app = JobApplication.objects.create(
            job=self.job,
            full_name="Fresh Applicant",
            email="fresh@example.com",
            phone="+233200000011",
            cover_letter="Letter",
            payment_status="paid",
            status="submitted",
        )
        self.client.login(username="detail_admin", password="pw")
        url = reverse("recruitment:school_application_detail", kwargs={"pk": app.pk})
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Select decision…")
        self.assertNotContains(r, 'value="submitted"')
        self.assertNotContains(r, 'value="pending_payment"')
        self.assertContains(r, 'value="shortlisted"')
        self.assertContains(r, 'value="hired"')

    def test_detail_dropdown_shortlisted_no_placeholder(self):
        app = JobApplication.objects.create(
            job=self.job,
            full_name="Shortlisted One",
            email="shortlisted@example.com",
            phone="+233200000022",
            cover_letter="Letter",
            payment_status="paid",
            status="shortlisted",
        )
        self.client.login(username="detail_admin", password="pw")
        url = reverse("recruitment:school_application_detail", kwargs={"pk": app.pk})
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Select decision…")
        self.assertNotContains(r, 'value="submitted"')
        self.assertContains(r, 'value="shortlisted"')
