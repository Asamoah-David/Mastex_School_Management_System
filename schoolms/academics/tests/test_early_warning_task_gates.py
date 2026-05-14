"""Feature gates on academics early-warning Celery helpers."""

import uuid
from datetime import date

from django.test import TestCase

from accounts.models import User
from academics.models import EarlyWarningFlag
from academics.tasks import _process_school_early_warnings, detect_early_warning_flags
from schools.models import School, SchoolFeature
from students.models import Student, StudentDiscipline


class ProcessSchoolEarlyWarningFeatureGateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="EW Proc School", subdomain=f"ewp-{uuid.uuid4().hex[:10]}")
        for key in ("early_warning", "attendance", "discipline"):
            SchoolFeature.objects.update_or_create(
                school=cls.school, key=key, defaults={"enabled": True}
            )
        cls.reporter = User.objects.create_user(
            username="ewp_rep", password="pw12345", school=cls.school, role="teacher"
        )
        cls.stu_user = User.objects.create_user(
            username="ewp_stu", password="pw12345", school=cls.school, role="student"
        )
        cls.student = Student.objects.create(
            school=cls.school,
            user=cls.stu_user,
            admission_number="EWP-1",
            class_name="1A",
            status="active",
        )

    def setUp(self):
        EarlyWarningFlag.objects.filter(school=self.school).delete()
        StudentDiscipline.objects.filter(school=self.school).delete()
        for key in ("early_warning", "attendance", "discipline"):
            SchoolFeature.objects.update_or_create(
                school=self.school, key=key, defaults={"enabled": True}
            )

    def test_no_flags_when_attendance_and_discipline_off(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="attendance", defaults={"enabled": False}
        )
        SchoolFeature.objects.update_or_create(
            school=self.school, key="discipline", defaults={"enabled": False}
        )
        c, u = _process_school_early_warnings(self.school.pk)
        self.assertEqual((c, u), (0, 0))

    def test_discipline_signal_when_discipline_on(self):
        for i in range(3):
            StudentDiscipline.objects.create(
                school=self.school,
                student=self.student,
                incident_type="minor",
                title=f"Inc {i}",
                description="test",
                incident_date=date.today(),
                reported_by=self.reporter,
            )
        c, u = _process_school_early_warnings(self.school.pk)
        self.assertGreaterEqual(c + u, 1)
        self.assertTrue(
            EarlyWarningFlag.objects.filter(school=self.school, student=self.student).exists()
        )


class DetectEarlyWarningFlagsAcademicsTaskTests(TestCase):
    """Academics ``detect_early_warning_flags`` skips schools without ``early_warning``."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="EW Det School", subdomain=f"ewd-{uuid.uuid4().hex[:10]}")
        SchoolFeature.objects.update_or_create(
            school=cls.school, key="early_warning", defaults={"enabled": False}
        )

    def test_returns_zero_counts_when_feature_off(self):
        out = detect_early_warning_flags.apply().result
        self.assertEqual(out.get("created"), 0)
        self.assertEqual(out.get("updated"), 0)
