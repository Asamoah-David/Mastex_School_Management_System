"""Feature gates on scheduled attendance / early-warning Celery tasks."""

import uuid
from datetime import date, timedelta
from unittest import mock

from django.test import TestCase

from academics.models import AcademicYear
from accounts.models import User
from core.tasks import detect_early_warning_flags, flag_attendance_early_warnings
from schools.models import School, SchoolFeature
from students.models import Student


class FlagAttendanceEarlyWarningTaskGatesTests(TestCase):
    """``flag_attendance_early_warnings`` skips schools without attendance + early_warning."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Gate FAT School", subdomain=f"fat-gate-{uuid.uuid4().hex[:10]}")

    @mock.patch("core.tasks._release_task_lock")
    @mock.patch("core.tasks._acquire_task_lock", return_value=True)
    @mock.patch("schools.features.is_feature_enabled_for_school", return_value=False)
    def test_notifies_zero_when_school_features_disabled(self, *_mocks):
        result = flag_attendance_early_warnings.apply().result
        self.assertEqual(result.get("notified"), 0)


class DetectEarlyWarningFlagsCoreTaskTests(TestCase):
    """``core.tasks.detect_early_warning_flags`` respects ``early_warning`` and sub-features."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Core EW School", subdomain=f"cew-{uuid.uuid4().hex[:10]}")

    def test_skips_school_when_early_warning_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="early_warning", defaults={"enabled": False}
        )
        out = detect_early_warning_flags.apply().result
        self.assertEqual(out.get("flags_created"), 0)
        self.assertEqual(out.get("students_scanned"), 0)

    def test_scans_students_but_creates_no_flags_when_signal_features_disabled(self):
        """EW on but attendance/results/discipline off → iterate students, no flags."""
        today = date.today()
        SchoolFeature.objects.update_or_create(
            school=self.school, key="early_warning", defaults={"enabled": True}
        )
        for key in ("attendance", "results", "discipline"):
            SchoolFeature.objects.update_or_create(
                school=self.school, key=key, defaults={"enabled": False}
            )
        AcademicYear.objects.create(
            school=self.school,
            name="Y1",
            start_date=today - timedelta(days=120),
            end_date=today + timedelta(days=120),
            is_current=True,
        )
        u = User.objects.create_user(
            username="cew_stu", password="pw12345", school=self.school, role="student"
        )
        Student.objects.create(
            school=self.school,
            user=u,
            admission_number="CEW-1",
            class_name="1A",
            status="active",
        )
        out = detect_early_warning_flags.apply().result
        self.assertGreaterEqual(out.get("students_scanned"), 1)
        self.assertEqual(out.get("flags_created"), 0)
