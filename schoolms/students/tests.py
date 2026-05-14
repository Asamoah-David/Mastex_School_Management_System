"""Leaver clearance and related student workflow tests."""

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from operations.models import Announcement
from schools.models import School, SchoolFeature
from datetime import date

from students.models import LearningPlan, Student, StudentClearance, StudentGuardian


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


class ParentChildGuardianAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Guardian School", subdomain="guardian-sch-01")
        cls.parent = User.objects.create_user(
            username="guard_parent", password="pw12345", school=cls.school, role="parent"
        )
        cls.other_parent = User.objects.create_user(
            username="guard_parent_other", password="pw12345", school=cls.school, role="parent"
        )
        cls.student_user = User.objects.create_user(
            username="guard_student", password="pw12345", school=cls.school, role="student"
        )
        cls.child = Student.objects.create(
            school=cls.school,
            user=cls.student_user,
            admission_number="GD-001",
            class_name="JHS 2",
            parent=None,
        )
        StudentGuardian.objects.create(
            school=cls.school,
            student=cls.child,
            guardian=cls.parent,
            relationship="guardian",
            is_primary=True,
        )

    def test_guardian_link_can_access_parent_child_detail(self):
        self.client.login(username="guard_parent", password="pw12345")
        resp = self.client.get(reverse("students:parent_child_detail", args=[self.child.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_unrelated_parent_cannot_access_parent_child_detail(self):
        self.client.login(username="guard_parent_other", password="pw12345")
        resp = self.client.get(reverse("students:parent_child_detail", args=[self.child.pk]))
        self.assertEqual(resp.status_code, 302)


class LearningPlanAccessTests(TestCase):
    """IEP / learning plans: only staff, linked guardians, legacy parent, or the student may open a plan."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="LP School", subdomain="lp-sch-01")
        cls.admin = User.objects.create_user(
            username="lp_admin", password="pw12345", school=cls.school, role="school_admin"
        )
        cls.parent = User.objects.create_user(
            username="lp_parent", password="pw12345", school=cls.school, role="parent"
        )
        cls.other_parent = User.objects.create_user(
            username="lp_parent_other", password="pw12345", school=cls.school, role="parent"
        )
        cls.student_user = User.objects.create_user(
            username="lp_student", password="pw12345", school=cls.school, role="student"
        )
        cls.student = Student.objects.create(
            school=cls.school,
            user=cls.student_user,
            admission_number="LP-001",
            class_name="1A",
            parent=None,
        )
        StudentGuardian.objects.create(
            school=cls.school,
            student=cls.student,
            guardian=cls.parent,
            relationship="guardian",
            is_primary=True,
        )
        cls.plan = LearningPlan.objects.create(
            school=cls.school,
            student=cls.student,
            plan_type="sen",
            status="draft",
            academic_year="2025/2026",
            start_date=date.today(),
            goals="Test goals for access control.",
            created_by=cls.admin,
            last_updated_by=cls.admin,
        )

    def setUp(self):
        self.client = Client()

    def test_guardian_can_view_plan(self):
        self.client.login(username="lp_parent", password="pw12345")
        r = self.client.get(reverse("students:learning_plan_detail", args=[self.plan.pk]))
        self.assertEqual(r.status_code, 200)

    def test_unrelated_parent_cannot_view_plan(self):
        self.client.login(username="lp_parent_other", password="pw12345")
        r = self.client.get(reverse("students:learning_plan_detail", args=[self.plan.pk]))
        self.assertEqual(r.status_code, 302)

    def test_guardian_cannot_activate_plan(self):
        self.client.login(username="lp_parent", password="pw12345")
        r = self.client.post(
            reverse("students:learning_plan_detail", args=[self.plan.pk]),
            {"action": "activate"},
        )
        self.assertEqual(r.status_code, 302)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, "draft")

    def test_admin_can_activate_plan(self):
        self.client.login(username="lp_admin", password="pw12345")
        r = self.client.post(
            reverse("students:learning_plan_detail", args=[self.plan.pk]),
            {"action": "activate"},
        )
        self.assertEqual(r.status_code, 302)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, "active")

    def test_learning_plans_feature_disabled_redirects_staff(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="learning_plans", defaults={"enabled": False}
        )
        self.client.login(username="lp_admin", password="pw12345")
        r = self.client.get(reverse("students:learning_plan_list"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)


class AnnouncementsListFeatureGateTests(TestCase):
    """Parent/student announcements list respects per-school announcements feature."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Ann List Sch", subdomain="ann-list-sch-01")
        SchoolFeature.objects.update_or_create(
            school=cls.school, key="announcements", defaults={"enabled": False}
        )
        cls.stu_user = User.objects.create_user(
            username="ann_list_stu", password="pw12345", school=cls.school, role="student"
        )
        cls.student = Student.objects.create(
            school=cls.school,
            user=cls.stu_user,
            admission_number="AL-01",
            class_name="1A",
        )
        cls.parent = User.objects.create_user(
            username="ann_list_parent", password="pw12345", school=cls.school, role="parent"
        )
        cls.student.parent = cls.parent
        cls.student.save(update_fields=["parent"])
        cls.hidden_ann = Announcement.objects.create(
            school=cls.school,
            title="HiddenDashAnn",
            content="x",
            target_audience="parents",
            created_by=cls.parent,
        )
        cls.hidden_stu_ann = Announcement.objects.create(
            school=cls.school,
            title="HiddenStuAnn",
            content="y",
            target_audience="students",
            created_by=cls.parent,
        )

    def setUp(self):
        self.client = Client()

    def test_student_redirected_when_announcements_disabled(self):
        self.client.login(username="ann_list_stu", password="pw12345")
        r = self.client.get(reverse("students:announcements_list"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("dashboard", r.url)

    def test_parent_redirected_when_announcements_disabled(self):
        self.client.login(username="ann_list_parent", password="pw12345")
        r = self.client.get(reverse("students:announcements_list"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("dashboard", r.url)

    def test_parent_dashboard_omits_announcements_when_disabled(self):
        self.client.login(username="ann_list_parent", password="pw12345")
        r = self.client.get(reverse("students:parent_dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "HiddenDashAnn")

    def test_student_portal_omits_announcements_when_disabled(self):
        self.client.login(username="ann_list_stu", password="pw12345")
        r = self.client.get(reverse("portal"))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "HiddenStuAnn")


class AbsenceAttendanceGateTests(TestCase):
    """Student absence flows respect SchoolFeature('attendance')."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Abs Gate Sch", subdomain="abs-gate-01")
        SchoolFeature.objects.update_or_create(
            school=cls.school, key="attendance", defaults={"enabled": False}
        )
        cls.stu_user = User.objects.create_user(
            username="abs_gate_stu", password="pw12345", school=cls.school, role="student"
        )
        cls.student = Student.objects.create(
            school=cls.school,
            user=cls.stu_user,
            admission_number="ABS-G1",
            class_name="1A",
        )
        cls.admin = User.objects.create_user(
            username="abs_gate_admin", password="pw12345", school=cls.school, role="school_admin"
        )

    def setUp(self):
        self.client = Client()

    def test_student_absence_create_redirects_when_attendance_disabled(self):
        self.client.login(username="abs_gate_stu", password="pw12345")
        r = self.client.get(reverse("students:absence_request_create"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("dashboard", r.url)

    def test_staff_absence_review_redirects_when_attendance_disabled(self):
        self.client.login(username="abs_gate_admin", password="pw12345")
        r = self.client.get(reverse("students:absence_requests_review"))
        self.assertEqual(r.status_code, 302)