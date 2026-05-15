"""Operations workflows: admissions pipeline, etc."""

import uuid
from datetime import date, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from finance.models import Fee, FeePayment
from academics.models import Subject
from operations.models import (
    AdmissionApplication,
    Announcement,
    ExamAnswer,
    ExamQuestion,
    ExamAttempt,
    OnlineExam,
    TimetableSlot,
    LibraryBook,
    LibraryIssue,
    LibraryFine,
    BusRoute,
    BusPayment,
    BusPaymentLedger,
    Hostel,
    HostelFee,
)
from operations.models.canteen import CanteenPayment
from operations.services.portal_payments import mark_bus_payment_completed, mark_canteen_payment_completed
from schools.models import School, SchoolFeature
from students.models import SchoolClass, Student, StudentGuardian


class AdmissionPipelineViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Ops Pipe School", subdomain="ops-pipe-sch-01")
        cls.admin = User.objects.create_user(
            username="ops_pipe_admin",
            password="pw12345",
            school=cls.school,
            role="school_admin",
        )
        cls.app = AdmissionApplication.objects.create(
            public_reference="ADM-TESTPIPE01",
            school=cls.school,
            first_name="A",
            last_name="B",
            date_of_birth="2015-01-01",
            gender="male",
            class_applied_for="1A",
            parent_first_name="P",
            parent_last_name="Q",
            parent_phone="0240000001",
            parent_email="p@example.com",
            address="Addr",
            status="pending",
        )

    def setUp(self):
        self.client = Client()

    def test_set_status_moves_pipeline(self):
        self.client.login(username="ops_pipe_admin", password="pw12345")
        url = reverse("operations:admission_set_status", args=[self.app.pk])
        r = self.client.post(url, {"status": "under_review"})
        self.assertEqual(r.status_code, 302)
        self.app.refresh_from_db()
        self.assertEqual(self.app.status, "under_review")

    def test_pipeline_board_renders(self):
        self.client.login(username="ops_pipe_admin", password="pw12345")
        r = self.client.get(reverse("operations:admission_pipeline"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Table view")

    def test_set_status_rejects_non_pipeline_values(self):
        """Terminal / unknown values must not be set via the pipeline endpoint."""
        self.client.login(username="ops_pipe_admin", password="pw12345")
        url = reverse("operations:admission_set_status", args=[self.app.pk])
        r = self.client.post(url, {"status": "approved"})
        self.assertEqual(r.status_code, 302)
        self.app.refresh_from_db()
        self.assertEqual(self.app.status, "pending")

    def test_set_status_noop_when_already_terminal(self):
        self.app.status = "approved"
        self.app.save(update_fields=["status"])
        self.client.login(username="ops_pipe_admin", password="pw12345")
        url = reverse("operations:admission_set_status", args=[self.app.pk])
        r = self.client.post(url, {"status": "under_review"})
        self.assertEqual(r.status_code, 302)
        self.app.refresh_from_db()
        self.assertEqual(self.app.status, "approved")


class StudentPaymentHistoryAccessTests(TestCase):
    """Parents must not view unrelated students' payment history (tenant + guardian)."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Pay Hist School", subdomain="pay-hist-sch-01")
        cls.parent_a = User.objects.create_user(
            username="pay_hist_parent_a", password="pw12345", school=cls.school, role="parent"
        )
        cls.parent_b = User.objects.create_user(
            username="pay_hist_parent_b", password="pw12345", school=cls.school, role="parent"
        )
        su_a = User.objects.create_user(
            username="pay_hist_stu_a", password="pw12345", school=cls.school, role="student"
        )
        su_b = User.objects.create_user(
            username="pay_hist_stu_b", password="pw12345", school=cls.school, role="student"
        )
        cls.child_a = Student.objects.create(
            school=cls.school,
            user=su_a,
            admission_number="PHA001",
            class_name="1A",
            parent=cls.parent_a,
        )
        cls.child_b = Student.objects.create(
            school=cls.school,
            user=su_b,
            admission_number="PHB002",
            class_name="1B",
            parent=cls.parent_b,
        )

    def setUp(self):
        self.client = Client()

    def test_parent_cannot_open_other_child_payment_history(self):
        self.client.login(username="pay_hist_parent_a", password="pw12345")
        url = reverse("operations:student_payment_history", args=[self.child_b.pk])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 302)

    def test_parent_can_open_own_child_payment_history(self):
        self.client.login(username="pay_hist_parent_a", password="pw12345")
        url = reverse("operations:student_payment_history", args=[self.child_a.pk])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)


class PaymentEndpointSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Ops Sec School", subdomain="ops-sec-sch-01")
        cls.admin = User.objects.create_user(
            username="ops_sec_admin", password="pw12345", school=cls.school, role="school_admin"
        )
        cls.parent_a = User.objects.create_user(
            username="ops_sec_parent_a", password="pw12345", school=cls.school, role="parent"
        )
        cls.parent_b = User.objects.create_user(
            username="ops_sec_parent_b", password="pw12345", school=cls.school, role="parent"
        )
        su_a = User.objects.create_user(
            username="ops_sec_stu_a", password="pw12345", school=cls.school, role="student"
        )
        su_b = User.objects.create_user(
            username="ops_sec_stu_b", password="pw12345", school=cls.school, role="student"
        )
        cls.child_a = Student.objects.create(
            school=cls.school, user=su_a, admission_number="OSA1", class_name="JHS1", parent=cls.parent_a
        )
        cls.child_b = Student.objects.create(
            school=cls.school, user=su_b, admission_number="OSB1", class_name="JHS1", parent=cls.parent_b
        )
        cls.canteen_payment = CanteenPayment.objects.create(
            school=cls.school,
            student=cls.child_b,
            amount="15.00",
            payment_reference="CANT-SEC-001",
            payment_status="pending",
        )

    def setUp(self):
        self.client = Client()

    def test_unrelated_parent_cannot_verify_other_child_payment(self):
        self.client.login(username="ops_sec_parent_a", password="pw12345")
        resp = self.client.get(
            reverse("operations:canteen_payment_verify"),
            {"payment_id": self.canteen_payment.pk},
        )
        self.assertEqual(resp.status_code, 302)
        self.canteen_payment.refresh_from_db()
        self.assertEqual(self.canteen_payment.payment_status, "pending")

    def test_non_finance_user_blocked_from_payment_dashboard(self):
        self.client.login(username="ops_sec_parent_a", password="pw12345")
        resp = self.client.get(reverse("operations:payment_dashboard"))
        self.assertEqual(resp.status_code, 302)

    def test_non_finance_user_blocked_from_record_payment(self):
        self.client.login(username="ops_sec_parent_a", password="pw12345")
        resp = self.client.get(reverse("operations:record_payment"))
        self.assertEqual(resp.status_code, 302)


class OnlineExamResultGuardianAccessTests(TestCase):
    """Linked guardians should see the student's online exam attempt summary."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="OE School", subdomain="oe-sch-01")
        cls.admin = User.objects.create_user(
            username="oe_admin", password="pw12345", school=cls.school, role="school_admin"
        )
        cls.parent = User.objects.create_user(
            username="oe_parent", password="pw12345", school=cls.school, role="parent"
        )
        cls.student_user = User.objects.create_user(
            username="oe_student", password="pw12345", school=cls.school, role="student"
        )
        cls.student = Student.objects.create(
            school=cls.school,
            user=cls.student_user,
            admission_number="OE-001",
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
        cls.subject = Subject.objects.create(school=cls.school, name="Science")
        now = timezone.now()
        cls.exam = OnlineExam.objects.create(
            school=cls.school,
            title="Midterm",
            subject=cls.subject,
            class_level="1A",
            duration_minutes=30,
            total_marks=Decimal("100"),
            passing_marks=Decimal("40"),
            start_time=now - timedelta(days=1),
            end_time=now + timedelta(days=1),
            status="published",
            show_results_immediately=True,
            created_by=cls.admin,
        )
        cls.attempt = ExamAttempt.objects.create(
            exam=cls.exam,
            student=cls.student,
            attempt_number=1,
            is_completed=True,
            score=Decimal("72"),
            is_passed=True,
            submitted_at=now,
        )

    def setUp(self):
        self.client = Client()

    def test_guardian_can_view_student_exam_result(self):
        self.client.login(username="oe_parent", password="pw12345")
        url = reverse("operations:online_exam_result", kwargs={"pk": self.attempt.pk})
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Midterm")


class OnlineExamResultGuardianBlockedWhenDisabledTests(TestCase):
    """Guardians must not view results when the school disables online exams."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="OE Off School", subdomain="oe-off-01")
        SchoolFeature.objects.update_or_create(
            school=cls.school, key="online_exams", defaults={"enabled": False}
        )
        cls.admin = User.objects.create_user(
            username="oe_off_admin", password="pw12345", school=cls.school, role="school_admin"
        )
        cls.parent = User.objects.create_user(
            username="oe_off_parent", password="pw12345", school=cls.school, role="parent"
        )
        cls.student_user = User.objects.create_user(
            username="oe_off_student", password="pw12345", school=cls.school, role="student"
        )
        cls.student = Student.objects.create(
            school=cls.school,
            user=cls.student_user,
            admission_number="OE-OFF-1",
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
        cls.subject = Subject.objects.create(school=cls.school, name="Art")
        now = timezone.now()
        cls.exam = OnlineExam.objects.create(
            school=cls.school,
            title="Hidden",
            subject=cls.subject,
            class_level="1A",
            duration_minutes=30,
            total_marks=Decimal("100"),
            passing_marks=Decimal("40"),
            start_time=now - timedelta(days=1),
            end_time=now + timedelta(days=1),
            status="published",
            show_results_immediately=True,
            created_by=cls.admin,
        )
        cls.attempt = ExamAttempt.objects.create(
            exam=cls.exam,
            student=cls.student,
            attempt_number=1,
            is_completed=True,
            score=Decimal("50"),
            is_passed=True,
            submitted_at=now,
        )

    def setUp(self):
        self.client = Client()

    def test_guardian_redirected_when_feature_off(self):
        self.client.login(username="oe_off_parent", password="pw12345")
        url = reverse("operations:online_exam_result", kwargs={"pk": self.attempt.pk})
        r = self.client.get(url)
        self.assertEqual(r.status_code, 302)

    def test_staff_can_view_when_feature_off(self):
        self.client.login(username="oe_off_admin", password="pw12345")
        url = reverse("operations:online_exam_result", kwargs={"pk": self.attempt.pk})
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Hidden")


class TimetableSlotScopedViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="TT Slot School", subdomain="ttslot-sch-01")
        cls.admin = User.objects.create_user(
            username="ttslot_admin", password="pw12345", school=cls.school, role="school_admin"
        )
        cls.teacher = User.objects.create_user(
            username="ttslot_teacher", password="pw12345", school=cls.school, role="teacher"
        )
        cls.parent = User.objects.create_user(
            username="ttslot_parent", password="pw12345", school=cls.school, role="parent"
        )
        cls.other_parent = User.objects.create_user(
            username="ttslot_parent_other", password="pw12345", school=cls.school, role="parent"
        )
        su = User.objects.create_user(
            username="ttslot_stu", password="pw12345", school=cls.school, role="student"
        )
        cls.student = Student.objects.create(
            school=cls.school,
            user=su,
            admission_number="TTS-01",
            class_name="1A",
            parent=cls.parent,
        )
        StudentGuardian.objects.create(
            school=cls.school,
            student=cls.student,
            guardian=cls.parent,
            relationship="mother",
            is_primary=True,
        )
        cls.subj = Subject.objects.create(school=cls.school, name="Eng")
        cls.subj_b = Subject.objects.create(school=cls.school, name="MathOnly2B")
        TimetableSlot.objects.create(
            school=cls.school,
            class_name="1A",
            day="monday",
            period_number=1,
            subject=cls.subj,
            teacher=cls.teacher,
            start_time=time(8, 0),
            end_time=time(9, 0),
            room="R1",
        )
        TimetableSlot.objects.create(
            school=cls.school,
            class_name="2B",
            day="monday",
            period_number=1,
            subject=cls.subj_b,
            teacher=cls.teacher,
            start_time=time(9, 0),
            end_time=time(10, 0),
            room="R2",
        )

    def setUp(self):
        self.client = Client()

    def test_parent_sees_only_linked_child_classes(self):
        self.client.login(username="ttslot_parent", password="pw12345")
        r = self.client.get(reverse("operations:timetable_view"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Eng")
        self.assertNotContains(r, "MathOnly2B")

    def test_unrelated_parent_sees_no_slots(self):
        self.client.login(username="ttslot_parent_other", password="pw12345")
        r = self.client.get(reverse("operations:timetable_view"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "No timetable entries")

    def test_teacher_sees_own_slots_only(self):
        self.client.login(username="ttslot_teacher", password="pw12345")
        r = self.client.get(reverse("operations:timetable_view"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Eng")
        self.assertContains(r, "MathOnly2B")


class OnlineExamEssayGradingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="OEG School", subdomain="oeg-sch-01")
        SchoolFeature.objects.update_or_create(
            school=cls.school, key="online_exams", defaults={"enabled": True}
        )
        cls.admin = User.objects.create_user(
            username="oeg_admin", password="pw12345", school=cls.school, role="school_admin"
        )
        cls.subj = Subject.objects.create(school=cls.school, name="Lit")
        now = timezone.now()
        cls.exam = OnlineExam.objects.create(
            school=cls.school,
            title="Mix",
            subject=cls.subj,
            class_level="1A",
            duration_minutes=60,
            total_marks=Decimal("10"),
            passing_marks=Decimal("4"),
            start_time=now - timedelta(days=1),
            end_time=now + timedelta(days=1),
            status="published",
            show_results_immediately=False,
            created_by=cls.admin,
        )
        cls.q_mcq = ExamQuestion.objects.create(
            exam=cls.exam,
            question_text="Pick",
            question_type="multiple_choice",
            marks=Decimal("4"),
            option_a="x",
            option_b="y",
            correct_answer="A",
            order=1,
        )
        cls.q_essay = ExamQuestion.objects.create(
            exam=cls.exam,
            question_text="Write",
            question_type="essay",
            marks=Decimal("6"),
            order=2,
        )
        su = User.objects.create_user(
            username="oeg_stu_u", password="pw12345", school=cls.school, role="student"
        )
        cls.student = Student.objects.create(
            school=cls.school,
            user=su,
            admission_number="OEG-1",
            class_name="1A",
        )
        cls.attempt = ExamAttempt.objects.create(
            exam=cls.exam,
            student=cls.student,
            attempt_number=1,
            is_completed=True,
            score=Decimal("4"),
            submitted_at=now,
        )
        cls.ans_mcq = ExamAnswer.objects.create(
            attempt=cls.attempt,
            question=cls.q_mcq,
            answer_given="A",
            is_correct=True,
            marks_obtained=Decimal("4"),
            teacher_reviewed=True,
        )
        cls.ans_essay = ExamAnswer.objects.create(
            attempt=cls.attempt,
            question=cls.q_essay,
            answer_given="draft",
            is_correct=False,
            marks_obtained=Decimal("0"),
            teacher_reviewed=False,
        )

    def setUp(self):
        self.client = Client()

    def test_post_cannot_inflate_mcq_marks(self):
        self.client.login(username="oeg_admin", password="pw12345")
        url = reverse("operations:online_exam_grade_attempt", kwargs={"attempt_id": self.attempt.pk})
        r = self.client.post(
            url,
            {
                f"marks_{self.ans_essay.pk}": "5",
                f"marks_{self.ans_mcq.pk}": "99",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.ans_mcq.refresh_from_db()
        self.ans_essay.refresh_from_db()
        self.assertEqual(self.ans_mcq.marks_obtained, Decimal("4"))
        self.assertEqual(self.ans_essay.marks_obtained, Decimal("5"))
        self.assertTrue(self.ans_essay.teacher_reviewed)


class AnnouncementFeatureGateTests(TestCase):
    """Staff announcement views respect SchoolFeature('announcements')."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Ann Feat School", subdomain="ann-feat-sch-01")
        SchoolFeature.objects.update_or_create(
            school=cls.school, key="announcements", defaults={"enabled": False}
        )
        cls.teacher = User.objects.create_user(
            username="ann_feat_teacher", password="pw12345", school=cls.school, role="teacher"
        )
        cls.admin = User.objects.create_user(
            username="ann_feat_admin", password="pw12345", school=cls.school, role="school_admin"
        )
        cls.ann = Announcement.objects.create(
            school=cls.school,
            title="Old",
            content="Body",
            target_audience="all",
            created_by=cls.admin,
        )

    def setUp(self):
        self.client = Client()

    def test_list_redirects_when_feature_disabled(self):
        self.client.login(username="ann_feat_teacher", password="pw12345")
        r = self.client.get(reverse("operations:announcement_list"))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(
            r.url.endswith(reverse("accounts:school_dashboard"))
            or reverse("accounts:school_dashboard") in r.url
        )

    def test_delete_redirects_when_feature_disabled(self):
        self.client.login(username="ann_feat_admin", password="pw12345")
        r = self.client.get(reverse("operations:announcement_delete", kwargs={"pk": self.ann.pk}))
        self.assertEqual(r.status_code, 302)

    def test_export_redirects_when_feature_disabled(self):
        self.client.login(username="ann_feat_admin", password="pw12345")
        r = self.client.get(reverse("operations:export_announcements"))
        self.assertEqual(r.status_code, 302)


class AdmissionFeatureGateTests(TestCase):
    """Admissions staff views, exports, apply, and track respect SchoolFeature('admission')."""

    @classmethod
    def setUpTestData(cls):
        cls.school_open = School.objects.create(name="Adm Open School", subdomain="adm-open-sch-01")
        cls.school_closed = School.objects.create(name="Adm Closed School", subdomain="adm-closed-sch-01")
        SchoolFeature.objects.update_or_create(
            school=cls.school_closed, key="admission", defaults={"enabled": False}
        )
        cls.admin_closed = User.objects.create_user(
            username="adm_closed_admin", password="pw12345", school=cls.school_closed, role="school_admin"
        )
        cls.app_closed = AdmissionApplication.objects.create(
            school=cls.school_closed,
            public_reference="ADM-GATE-TESTREF01",
            first_name="Gate",
            last_name="Applicant",
            date_of_birth=date(2018, 1, 1),
            gender="male",
            class_applied_for="1A",
            parent_first_name="P",
            parent_last_name="Q",
            parent_phone="5551234001",
            address="Addr",
            status="pending",
        )

    def setUp(self):
        self.client = Client()

    def test_list_redirects_when_admission_disabled(self):
        self.client.login(username="adm_closed_admin", password="pw12345")
        r = self.client.get(reverse("operations:admission_list"))
        self.assertEqual(r.status_code, 302)

    def test_pipeline_redirects_when_admission_disabled(self):
        self.client.login(username="adm_closed_admin", password="pw12345")
        r = self.client.get(reverse("operations:admission_pipeline"))
        self.assertEqual(r.status_code, 302)

    def test_export_redirects_when_admission_disabled(self):
        self.client.login(username="adm_closed_admin", password="pw12345")
        r = self.client.get(reverse("operations:export_admissions"))
        self.assertEqual(r.status_code, 302)

    def test_apply_form_excludes_closed_school(self):
        r = self.client.get(reverse("operations:admission_apply"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Adm Open School")
        self.assertNotContains(r, "Adm Closed School")

    def test_apply_post_rejects_disabled_school_tamper(self):
        before = AdmissionApplication.objects.filter(school=self.school_closed).count()
        r = self.client.post(
            reverse("operations:admission_apply"),
            {
                "first_name": "X",
                "last_name": "Y",
                "date_of_birth": "2018-05-01",
                "gender": "male",
                "class_applied_for": "1A",
                "parent_first_name": "Pa",
                "parent_last_name": "Ma",
                "parent_phone": "5559990001",
                "address": "Here",
                "school": str(self.school_closed.pk),
            },
        )
        self.assertEqual(r.status_code, 200)
        after = AdmissionApplication.objects.filter(school=self.school_closed).count()
        self.assertEqual(after, before)

    def test_track_hides_when_school_admission_disabled(self):
        r = self.client.get(
            reverse("operations:admission_track"), {"ref": self.app_closed.public_reference}
        )
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Gate")


class AdmissionAccessAndValidationTests(TestCase):
    """Narrow staff access, class roster validation, and stricter public tracking."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Adm Access School", subdomain="adm-access-sch")
        cls.teacher = User.objects.create_user(
            username="adm_access_teacher", password="pw", school=cls.school, role="teacher"
        )
        cls.officer = User.objects.create_user(
            username="adm_access_officer", password="pw", school=cls.school, role="admission_officer"
        )
        cls.accountant = User.objects.create_user(
            username="adm_access_acct", password="pw", school=cls.school, role="accountant"
        )
        SchoolClass.objects.create(school=cls.school, name="P1A")

    def setUp(self):
        self.client = Client()

    def test_teacher_denied_admission_list(self):
        self.client.login(username="adm_access_teacher", password="pw")
        r = self.client.get(reverse("operations:admission_list"))
        self.assertEqual(r.status_code, 302)

    def test_admission_officer_can_open_list(self):
        self.client.login(username="adm_access_officer", password="pw")
        r = self.client.get(reverse("operations:admission_list"))
        self.assertEqual(r.status_code, 200)

    def test_accountant_denied_admission_export(self):
        self.client.login(username="adm_access_acct", password="pw")
        r = self.client.get(reverse("operations:export_admissions"))
        self.assertEqual(r.status_code, 302)

    def test_apply_rejects_class_not_in_schoolclass_roster(self):
        payload = {
            "first_name": "Kid",
            "last_name": "Zed",
            "date_of_birth": "2018-05-01",
            "gender": "male",
            "class_applied_for": "NOT-A-REALCLASS",
            "parent_first_name": "Pa",
            "parent_last_name": "Zed",
            "parent_phone": "0244111222",
            "address": "Here",
            "school": str(self.school.pk),
        }
        before = AdmissionApplication.objects.filter(school=self.school).count()
        r = self.client.post(reverse("operations:admission_apply"), payload)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(AdmissionApplication.objects.filter(school=self.school).count(), before)

    def test_track_phone_name_ambiguous_shows_message(self):
        base = dict(
            school=self.school,
            first_name="Same",
            last_name="Child",
            date_of_birth=date(2018, 1, 1),
            gender="male",
            class_applied_for="P1A",
            parent_first_name="P",
            parent_last_name="Zed",
            parent_phone="0244000001",
            address="A",
            status="pending",
        )
        AdmissionApplication.objects.create(public_reference="ADM-DUP1", **base)
        AdmissionApplication.objects.create(
            public_reference="ADM-DUP2",
            **{**base, "date_of_birth": date(2018, 1, 2)},
        )
        r = self.client.get(
            reverse("operations:admission_track"),
            {"phone": "0244000001", "name": "Same Child"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Multiple applications matched")


class AdmissionBulkRejectTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Bulk Adm School", subdomain="bulk-adm-sch")
        User.objects.create_user(
            username="bulk_adm_admin", password="pw", school=cls.school, role="school_admin"
        )
        cls.a1 = AdmissionApplication.objects.create(
            public_reference="ADM-BULK01",
            school=cls.school,
            first_name="A",
            last_name="One",
            date_of_birth=date(2017, 1, 1),
            gender="male",
            class_applied_for="P1A",
            parent_first_name="P",
            parent_last_name="One",
            parent_phone="0244111001",
            address="Addr",
            status="pending",
        )
        cls.a2 = AdmissionApplication.objects.create(
            public_reference="ADM-BULK02",
            school=cls.school,
            first_name="B",
            last_name="Two",
            date_of_birth=date(2017, 1, 2),
            gender="male",
            class_applied_for="P1A",
            parent_first_name="P",
            parent_last_name="Two",
            parent_phone="0244111002",
            address="Addr",
            status="pending",
        )

    def setUp(self):
        self.client = Client()

    def test_bulk_reject_selected(self):
        self.client.login(username="bulk_adm_admin", password="pw")
        r = self.client.post(
            reverse("operations:admission_list"),
            {"bulk_action": "reject", "selected_ids": [str(self.a1.pk), str(self.a2.pk)]},
        )
        self.assertEqual(r.status_code, 302)
        self.a1.refresh_from_db()
        self.a2.refresh_from_db()
        self.assertEqual(self.a1.status, "rejected")
        self.assertEqual(self.a2.status, "rejected")


class AttendanceDisciplineFeatureGateTests(TestCase):
    """Attendance / discipline staff views and exports respect school features."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Att Gate School", subdomain="att-gate-sch-01")
        SchoolFeature.objects.update_or_create(
            school=cls.school, key="attendance", defaults={"enabled": False}
        )
        SchoolFeature.objects.update_or_create(
            school=cls.school, key="discipline", defaults={"enabled": False}
        )
        cls.teacher = User.objects.create_user(
            username="att_gate_teacher", password="pw12345", school=cls.school, role="teacher"
        )
        cls.admin = User.objects.create_user(
            username="att_gate_admin", password="pw12345", school=cls.school, role="school_admin"
        )
        cls.parent = User.objects.create_user(
            username="att_gate_parent", password="pw12345", school=cls.school, role="parent"
        )
        su = User.objects.create_user(
            username="att_gate_stu", password="pw12345", school=cls.school, role="student"
        )
        cls.student = Student.objects.create(
            school=cls.school,
            user=su,
            admission_number="ATG-01",
            class_name="1A",
            parent=cls.parent,
        )

    def setUp(self):
        self.client = Client()

    def test_attendance_list_redirects_when_feature_off(self):
        self.client.login(username="att_gate_teacher", password="pw12345")
        r = self.client.get(reverse("operations:attendance_list"))
        self.assertEqual(r.status_code, 302)

    def test_attendance_mark_redirects_when_feature_off(self):
        self.client.login(username="att_gate_teacher", password="pw12345")
        r = self.client.get(reverse("operations:attendance_mark"))
        self.assertEqual(r.status_code, 302)

    def test_parent_cannot_open_attendance_list_even_when_feature_on(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="attendance", defaults={"enabled": True}
        )
        self.client.login(username="att_gate_parent", password="pw12345")
        r = self.client.get(reverse("operations:attendance_list"))
        self.assertEqual(r.status_code, 302)

    def test_discipline_staff_list_redirects_when_feature_off(self):
        self.client.login(username="att_gate_admin", password="pw12345")
        r = self.client.get(reverse("operations:discipline_list"))
        self.assertEqual(r.status_code, 302)

    def test_parent_discipline_redirects_when_feature_off(self):
        self.client.login(username="att_gate_parent", password="pw12345")
        r = self.client.get(reverse("operations:discipline_list"))
        self.assertEqual(r.status_code, 302)

    def test_export_attendance_redirects_when_feature_off(self):
        self.client.login(username="att_gate_admin", password="pw12345")
        r = self.client.get(reverse("operations:export_attendance"))
        self.assertEqual(r.status_code, 302)

    def test_export_discipline_redirects_when_feature_off(self):
        self.client.login(username="att_gate_admin", password="pw12345")
        r = self.client.get(reverse("operations:export_discipline"))
        self.assertEqual(r.status_code, 302)


class AttendanceAnalyticsGateTests(TestCase):
    """Chronic absenteeism report requires both attendance and attendance_analytics."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Ana School", subdomain="ana-sch-gate-01")
        SchoolFeature.objects.update_or_create(
            school=cls.school, key="attendance", defaults={"enabled": True}
        )
        SchoolFeature.objects.update_or_create(
            school=cls.school, key="attendance_analytics", defaults={"enabled": True}
        )
        cls.admin = User.objects.create_user(
            username="ana_admin", password="pw12345", school=cls.school, role="school_admin"
        )

    def setUp(self):
        self.client = Client()
        SchoolFeature.objects.update_or_create(
            school=self.school, key="attendance", defaults={"enabled": True}
        )
        SchoolFeature.objects.update_or_create(
            school=self.school, key="attendance_analytics", defaults={"enabled": True}
        )

    def test_redirect_when_core_attendance_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="attendance", defaults={"enabled": False}
        )
        SchoolFeature.objects.update_or_create(
            school=self.school, key="attendance_analytics", defaults={"enabled": True}
        )
        self.client.login(username="ana_admin", password="pw12345")
        r = self.client.get(reverse("operations:attendance_analytics"))
        self.assertEqual(r.status_code, 302)

    def test_redirect_when_analytics_addon_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="attendance", defaults={"enabled": True}
        )
        SchoolFeature.objects.update_or_create(
            school=self.school, key="attendance_analytics", defaults={"enabled": False}
        )
        self.client.login(username="ana_admin", password="pw12345")
        r = self.client.get(reverse("operations:attendance_analytics"))
        self.assertEqual(r.status_code, 302)

    def test_renders_when_both_enabled(self):
        self.client.login(username="ana_admin", password="pw12345")
        r = self.client.get(reverse("operations:attendance_analytics"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Attendance Analytics")


class SchoolRankingsFeatureGateTests(TestCase):
    """Class rankings (operations:school_rankings) requires performance_analytics; respects attendance flag."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Rank School", subdomain=f"rank-sch-{uuid.uuid4().hex[:10]}")
        for key, on in (
            ("performance_analytics", True),
            ("attendance", True),
        ):
            SchoolFeature.objects.update_or_create(school=cls.school, key=key, defaults={"enabled": on})
        cls.admin = User.objects.create_user(
            username="rank_admin", password="pw12345", school=cls.school, role="school_admin"
        )
        cls.student_user = User.objects.create_user(
            username="rank_stu", password="pw12345", school=cls.school, role="student"
        )
        cls.student = Student.objects.create(
            school=cls.school,
            user=cls.student_user,
            admission_number="R-1",
            class_name="1A",
            status="active",
        )

    def setUp(self):
        self.client = Client()
        for key, on in (
            ("performance_analytics", True),
            ("attendance", True),
        ):
            SchoolFeature.objects.update_or_create(school=self.school, key=key, defaults={"enabled": on})

    def test_redirect_when_performance_analytics_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="performance_analytics", defaults={"enabled": False}
        )
        self.client.login(username="rank_admin", password="pw12345")
        r = self.client.get(reverse("operations:school_rankings"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)

    def test_attendance_column_dash_when_attendance_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="attendance", defaults={"enabled": False}
        )
        self.client.login(username="rank_admin", password="pw12345")
        r = self.client.get(reverse("operations:school_rankings"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Rankings use average scores only")


class EarlyWarningListFeatureGateTests(TestCase):
    """Early warning list redirects to school dashboard when the feature is off."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="EW School", subdomain=f"ew-sch-{uuid.uuid4().hex[:10]}")
        SchoolFeature.objects.update_or_create(
            school=cls.school, key="early_warning", defaults={"enabled": True}
        )
        cls.admin = User.objects.create_user(
            username="ew_admin", password="pw12345", school=cls.school, role="school_admin"
        )

    def setUp(self):
        self.client = Client()
        SchoolFeature.objects.update_or_create(
            school=self.school, key="early_warning", defaults={"enabled": True}
        )

    def test_redirect_when_feature_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="early_warning", defaults={"enabled": False}
        )
        self.client.login(username="ew_admin", password="pw12345")
        r = self.client.get(reverse("operations:early_warning_list"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)


class SchoolOperationsFeatureGateTests(TestCase):
    """School operations views respect SchoolFeature flags (portal + staff surfaces)."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Ops Gate School", subdomain=f"ops-gate-{uuid.uuid4().hex[:10]}")
        cls.admin = User.objects.create_user(
            username="ops_gate_admin", password="pw12345", school=cls.school, role="school_admin"
        )
        cls.stu_user = User.objects.create_user(
            username="ops_gate_stu", password="pw12345", school=cls.school, role="student"
        )
        cls.student = Student.objects.create(
            school=cls.school,
            user=cls.stu_user,
            admission_number="OGS-01",
            class_name="1A",
        )

    def setUp(self):
        self.client = Client()

    def test_bus_my_redirects_when_bus_transport_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="bus_transport", defaults={"enabled": False}
        )
        self.client.login(username="ops_gate_stu", password="pw12345")
        r = self.client.get(reverse("operations:bus_my"))
        self.assertEqual(r.status_code, 302)

    def test_textbook_my_redirects_when_textbooks_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="textbooks", defaults={"enabled": False}
        )
        self.client.login(username="ops_gate_stu", password="pw12345")
        r = self.client.get(reverse("operations:textbook_my"))
        self.assertEqual(r.status_code, 302)

    def test_canteen_my_redirects_when_canteen_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="canteen", defaults={"enabled": False}
        )
        self.client.login(username="ops_gate_stu", password="pw12345")
        r = self.client.get(reverse("operations:canteen_my"))
        self.assertEqual(r.status_code, 302)

    def test_hostel_my_redirects_when_hostel_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="hostel", defaults={"enabled": False}
        )
        self.client.login(username="ops_gate_stu", password="pw12345")
        r = self.client.get(reverse("operations:hostel_my"))
        self.assertEqual(r.status_code, 302)

    def test_certificate_list_redirects_when_certificates_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="certificates", defaults={"enabled": False}
        )
        self.client.login(username="ops_gate_admin", password="pw12345")
        r = self.client.get(reverse("operations:certificate_list"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)

    def test_document_list_redirects_when_documents_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="documents", defaults={"enabled": False}
        )
        self.client.login(username="ops_gate_admin", password="pw12345")
        r = self.client.get(reverse("operations:document_list"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)

    def test_health_record_list_redirects_when_health_records_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="health_records", defaults={"enabled": False}
        )
        self.client.login(username="ops_gate_admin", password="pw12345")
        r = self.client.get(reverse("operations:health_record_list"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)

    def test_inventory_list_redirects_when_inventory_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="inventory", defaults={"enabled": False}
        )
        self.client.login(username="ops_gate_admin", password="pw12345")
        r = self.client.get(reverse("operations:inventory_category_list"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)

    def test_exam_hall_list_redirects_when_exams_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="exams", defaults={"enabled": False}
        )
        self.client.login(username="ops_gate_admin", password="pw12345")
        r = self.client.get(reverse("operations:exam_hall_list"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)

    def test_auto_seating_plan_redirects_when_exams_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="exams", defaults={"enabled": False}
        )
        self.client.login(username="ops_gate_admin", password="pw12345")
        r = self.client.get(reverse("operations:auto_seating_plan_page"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)

    def test_generate_seating_plan_redirects_when_exams_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="exams", defaults={"enabled": False}
        )
        self.client.login(username="ops_gate_admin", password="pw12345")
        r = self.client.get(reverse("operations:generate_seating_plan"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)

    def test_id_card_list_redirects_when_id_cards_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="id_cards", defaults={"enabled": False}
        )
        self.client.login(username="ops_gate_admin", password="pw12345")
        r = self.client.get(reverse("operations:id_card_list"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)

    def test_library_fine_mark_paid_redirects_when_library_disabled(self):
        book = LibraryBook.objects.create(
            school=self.school,
            isbn="9780000000001",
            title="Gate Book",
            author="A",
            total_copies=1,
            available_copies=1,
        )
        issue = LibraryIssue.objects.create(
            school=self.school,
            student=self.student,
            book=book,
            issue_date=date.today(),
            due_date=date.today(),
            status="issued",
            issued_by=self.admin,
        )
        fine = LibraryFine.objects.create(
            school=self.school,
            issue=issue,
            fine_amount=Decimal("10.00"),
        )
        SchoolFeature.objects.update_or_create(
            school=self.school, key="library", defaults={"enabled": False}
        )
        self.client.login(username="ops_gate_admin", password="pw12345")
        r = self.client.post(
            reverse("operations:library_fine_mark_paid", kwargs={"pk": fine.pk}),
            {"amount": "10.00"},
        )
        self.assertEqual(r.status_code, 302)


class ExpensesBudgetFeatureGateTests(TestCase):
    """Expense and budget views require SchoolFeature('expenses' / 'budgets')."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Exp Budget Gate", subdomain=f"exp-bud-{uuid.uuid4().hex[:10]}")
        cls.admin = User.objects.create_user(
            username="exp_bud_admin", password="pw12345", school=cls.school, role="school_admin"
        )

    def setUp(self):
        self.client = Client()

    def test_expense_list_redirects_when_expenses_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="expenses", defaults={"enabled": False}
        )
        self.client.login(username="exp_bud_admin", password="pw12345")
        r = self.client.get(reverse("operations:expense_list"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)

    def test_budget_list_redirects_when_budgets_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="budgets", defaults={"enabled": False}
        )
        self.client.login(username="exp_bud_admin", password="pw12345")
        r = self.client.get(reverse("operations:budget_list"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)


class RecordPaymentFeatureGateTests(TestCase):
    """record_payment requires at least one payment module to be enabled."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Rec Pay Gate", subdomain=f"rec-pay-{uuid.uuid4().hex[:10]}")
        for key in ("fee_management", "canteen", "bus_transport", "textbooks", "hostel"):
            SchoolFeature.objects.update_or_create(school=cls.school, key=key, defaults={"enabled": False})
        cls.bursar = User.objects.create_user(
            username="rec_pay_bursar", password="pw12345", school=cls.school, role="school_admin"
        )

    def setUp(self):
        self.client = Client()

    def test_record_payment_redirects_when_all_payment_modules_disabled(self):
        self.client.login(username="rec_pay_bursar", password="pw12345")
        r = self.client.get(reverse("operations:record_payment"))
        self.assertRedirects(r, reverse("accounts:dashboard"), fetch_redirect_response=False)


class PortalPaymentMarkCompletedTests(TestCase):
    """Paystack completion helpers must keep amount_paid aligned and be idempotent."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Portal Mark", subdomain=f"portal-mk-{uuid.uuid4().hex[:8]}")
        su = User.objects.create_user(
            username="portal_mk_stu", password="pw12345", school=cls.school, role="student"
        )
        cls.student = Student.objects.create(
            school=cls.school,
            user=su,
            admission_number="PMK-01",
            class_name="1A",
        )

    def setUp(self):
        self._p_tx = patch("operations.services.portal_payments.record_payment_transaction", autospec=True)
        self._p_led = patch("operations.services.portal_payments._record_to_school_ledger", autospec=True)
        self._p_tx.start()
        self._p_led.start()
        self.addCleanup(self._p_tx.stop)
        self.addCleanup(self._p_led.stop)

    def test_mark_canteen_payment_completed_sets_amount_paid_and_history(self):
        p = CanteenPayment.objects.create(
            school=self.school,
            student=self.student,
            amount=Decimal("12.00"),
            description="Lunch",
            payment_reference="CANT_REF_MARK",
            payment_status="pending",
        )
        mark_canteen_payment_completed(payment=p, reference="CANT_REF_MARK")
        p.refresh_from_db()
        self.assertEqual(p.payment_status, "completed")
        self.assertEqual(p.amount_paid, Decimal("12.00"))
        self.assertIsInstance(p.payment_history, list)
        self.assertGreaterEqual(len(p.payment_history), 1)

    def test_mark_canteen_payment_completed_idempotent(self):
        p = CanteenPayment.objects.create(
            school=self.school,
            student=self.student,
            amount=Decimal("5.00"),
            payment_reference="CANT_REF_IDEM",
            payment_status="pending",
        )
        mark_canteen_payment_completed(payment=p, reference="CANT_REF_IDEM")
        mark_canteen_payment_completed(payment=p, reference="CANT_REF_IDEM")
        p.refresh_from_db()
        self.assertEqual(p.amount_paid, Decimal("5.00"))

    def test_mark_bus_payment_completed_sets_amount_paid(self):
        route = BusRoute.objects.create(
            school=self.school,
            name="R1",
            fee_per_term=Decimal("40.00"),
            payment_frequency="term",
        )
        bp = BusPayment.objects.create(
            school=self.school,
            student=self.student,
            route=route,
            amount=Decimal("40.00"),
            term_period="T1",
            daily_units=0,
            payment_reference="BUS_REF_MARK",
            payment_status="pending",
        )
        mark_bus_payment_completed(payment=bp, reference="BUS_REF_MARK")
        bp.refresh_from_db()
        self.assertTrue(bp.paid)
        self.assertEqual(bp.amount_paid, Decimal("40.00"))
        self.assertEqual(bp.payment_status, "completed")


class RecordPaymentOfflineFlowTests(TestCase):
    """Cash / offline paths on record_payment keep models and daily bus math consistent."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Rec Flow", subdomain=f"rec-fl-{uuid.uuid4().hex[:8]}")
        for key in ("fee_management", "canteen", "bus_transport", "hostel"):
            SchoolFeature.objects.update_or_create(school=cls.school, key=key, defaults={"enabled": True})
        cls.admin = User.objects.create_user(
            username="rec_flow_admin", password="pw12345", school=cls.school, role="school_admin"
        )
        su = User.objects.create_user(
            username="rec_flow_stu", password="pw12345", school=cls.school, role="student"
        )
        cls.student = Student.objects.create(
            school=cls.school,
            user=su,
            admission_number="RF001",
            class_name="1A",
        )
        cls.route_term = BusRoute.objects.create(
            school=cls.school,
            name="North",
            fee_per_term=Decimal("100.00"),
            payment_frequency="term",
        )
        cls.route_daily = BusRoute.objects.create(
            school=cls.school,
            name="South Daily",
            fee_per_term=Decimal("5.00"),
            payment_frequency="daily",
        )
        cls.route_weekly = BusRoute.objects.create(
            school=cls.school,
            name="West Weekly",
            fee_per_term=Decimal("80.00"),
            payment_frequency="weekly",
        )
        cls.hostel = Hostel.objects.create(school=cls.school, name="Block A", type="Boys", total_beds=20)
        cls.hostel_fee = HostelFee.objects.create(
            school=cls.school,
            student=cls.student,
            hostel=cls.hostel,
            amount=Decimal("200.00"),
            amount_paid=Decimal("0"),
            term="Term 1 2026",
            paid=False,
        )

    def setUp(self):
        self.client = Client()

    def test_offline_canteen_sets_amount_paid_and_history(self):
        self.client.login(username="rec_flow_admin", password="pw12345")
        url = reverse("operations:record_payment")
        self.client.post(
            url,
            {
                "payment_type": "canteen",
                "payment_method": "cash",
                "student": str(self.student.pk),
                "canteen_amount": "8.50",
                "payment_frequency": "daily",
                "daily_units": "2",
                "description": "Breakfast",
            },
        )
        row = CanteenPayment.objects.filter(student=self.student).order_by("-id").first()
        self.assertIsNotNone(row)
        self.assertEqual(row.amount_paid, Decimal("8.50"))
        self.assertEqual(row.payment_status, "completed")
        self.assertEqual(row.daily_units, 2)
        self.assertTrue(any(h.get("reference", "").startswith("CASH_CANTEEN_") for h in (row.payment_history or [])))

    def test_offline_bus_daily_rejects_wrong_total(self):
        self.client.login(username="rec_flow_admin", password="pw12345")
        url = reverse("operations:record_payment")
        before = BusPayment.objects.filter(student=self.student).count()
        self.client.post(
            url,
            {
                "payment_type": "bus",
                "payment_method": "cash",
                "student": str(self.student.pk),
                "amount": "20.00",
                "term": "Term 1 2026",
                "bus_route_id": str(self.route_daily.pk),
                "bus_daily_units": "5",
            },
        )
        self.assertEqual(BusPayment.objects.filter(student=self.student).count(), before)

    def test_offline_bus_daily_accepts_fee_times_days(self):
        self.client.login(username="rec_flow_admin", password="pw12345")
        url = reverse("operations:record_payment")
        self.client.post(
            url,
            {
                "payment_type": "bus",
                "payment_method": "cash",
                "student": str(self.student.pk),
                "amount": "25.00",
                "term": "Term 1 2026",
                "bus_route_id": str(self.route_daily.pk),
                "bus_daily_units": "5",
            },
        )
        bp = BusPayment.objects.filter(student=self.student, route=self.route_daily).order_by("-id").first()
        self.assertIsNotNone(bp)
        self.assertEqual(bp.daily_units, 5)
        self.assertEqual(bp.amount_paid, Decimal("25.00"))
        self.assertTrue(bp.paid)
        self.assertTrue(BusPaymentLedger.objects.filter(bus_payment=bp).exists())

    def test_offline_bus_term_rejects_wrong_amount(self):
        self.client.login(username="rec_flow_admin", password="pw12345")
        url = reverse("operations:record_payment")
        before = BusPayment.objects.filter(student=self.student).count()
        self.client.post(
            url,
            {
                "payment_type": "bus",
                "payment_method": "cash",
                "student": str(self.student.pk),
                "amount": "99.00",
                "term": "Term 1 2026",
                "bus_route_id": str(self.route_term.pk),
            },
        )
        self.assertEqual(BusPayment.objects.filter(student=self.student).count(), before)

    def test_offline_bus_term_accepts_listed_fee(self):
        self.client.login(username="rec_flow_admin", password="pw12345")
        url = reverse("operations:record_payment")
        self.client.post(
            url,
            {
                "payment_type": "bus",
                "payment_method": "cash",
                "student": str(self.student.pk),
                "amount": "100.00",
                "term": "Term 1 2026",
                "bus_route_id": str(self.route_term.pk),
            },
        )
        bp = BusPayment.objects.filter(student=self.student, route=self.route_term).order_by("-id").first()
        self.assertIsNotNone(bp)
        self.assertEqual(bp.amount_paid, Decimal("100.00"))

    def test_offline_bus_weekly_accepts_listed_fee(self):
        self.client.login(username="rec_flow_admin", password="pw12345")
        url = reverse("operations:record_payment")
        self.client.post(
            url,
            {
                "payment_type": "bus",
                "payment_method": "cash",
                "student": str(self.student.pk),
                "amount": "80.00",
                "term": "Term 1 2026",
                "bus_route_id": str(self.route_weekly.pk),
            },
        )
        bp = BusPayment.objects.filter(student=self.student, route=self.route_weekly).order_by("-id").first()
        self.assertIsNotNone(bp)
        self.assertEqual(bp.amount_paid, Decimal("80.00"))

    def test_offline_hostel_partial_updates_balance(self):
        self.client.login(username="rec_flow_admin", password="pw12345")
        url = reverse("operations:record_payment")
        self.client.post(
            url,
            {
                "payment_type": "hostel",
                "payment_method": "cash",
                "student": str(self.student.pk),
                "hostel_fee_id": str(self.hostel_fee.pk),
                "hostel_amount": "50.00",
            },
        )
        self.hostel_fee.refresh_from_db()
        self.assertEqual(self.hostel_fee.amount_paid, Decimal("50.00"))
        self.assertFalse(self.hostel_fee.paid)
        self.assertEqual(self.hostel_fee.payment_status, "partial")

    def test_offline_school_fee_rejects_overpayment(self):
        fee = Fee.objects.create(
            school=self.school,
            student=self.student,
            amount=Decimal("200.00"),
            amount_paid=Decimal("0"),
            description="Term fees",
        )
        self.client.login(username="rec_flow_admin", password="pw12345")
        url = reverse("operations:record_payment")
        self.client.post(
            url,
            {
                "payment_type": "school_fee",
                "payment_method": "cash",
                "school_fee_student_id": str(self.student.pk),
                "fee_id": str(fee.pk),
                "school_fee_amount": "250.00",
            },
        )
        fee.refresh_from_db()
        self.assertEqual(fee.amount_paid, Decimal("0"))

    def test_offline_school_fee_partial_records(self):
        fee = Fee.objects.create(
            school=self.school,
            student=self.student,
            amount=Decimal("200.00"),
            amount_paid=Decimal("0"),
            description="Term fees",
        )
        self.client.login(username="rec_flow_admin", password="pw12345")
        url = reverse("operations:record_payment")
        self.client.post(
            url,
            {
                "payment_type": "school_fee",
                "payment_method": "cash",
                "school_fee_student_id": str(self.student.pk),
                "fee_id": str(fee.pk),
                "school_fee_amount": "50.00",
            },
        )
        fee.refresh_from_db()
        self.assertEqual(fee.amount_paid, Decimal("50.00"))
        self.assertFalse(fee.paid)

    def test_combined_payment_records_school_fee_and_canteen_atomically(self):
        fee = Fee.objects.create(
            school=self.school,
            student=self.student,
            amount=Decimal("200.00"),
            amount_paid=Decimal("0"),
            description="Term fees",
        )
        self.client.login(username="rec_flow_admin", password="pw12345")
        url = reverse("operations:record_payment")
        body = {
            "payment_type": "combined",
            "payment_method": "cash",
            "student": str(self.student.pk),
            f"combined_sf_amount_{fee.pk}": "40.00",
            "combined_canteen_amount": "12.00",
            "combined_payment_frequency": "single",
            "combined_description": "Lunch bundle",
        }
        r = self.client.post(url, body)
        self.assertEqual(r.status_code, 302)
        fee.refresh_from_db()
        self.assertEqual(fee.amount_paid, Decimal("40.00"))
        self.assertTrue(
            CanteenPayment.objects.filter(
                student=self.student,
                amount=Decimal("12.00"),
                payment_status="completed",
            ).exists()
        )

    def test_combined_payment_rolls_back_if_bus_amount_invalid(self):
        fee = Fee.objects.create(
            school=self.school,
            student=self.student,
            amount=Decimal("100.00"),
            amount_paid=Decimal("0"),
            description="Only fee",
        )
        self.client.login(username="rec_flow_admin", password="pw12345")
        url = reverse("operations:record_payment")
        r = self.client.post(
            url,
            {
                "payment_type": "combined",
                "payment_method": "cash",
                "student": str(self.student.pk),
                f"combined_sf_amount_{fee.pk}": "25.00",
                "combined_bus_route_id": str(self.route_term.pk),
                "combined_bus_amount": "99.00",
                "combined_bus_term": "T1",
            },
        )
        self.assertEqual(r.status_code, 302)
        fee.refresh_from_db()
        self.assertEqual(fee.amount_paid, Decimal("0"))
        self.assertFalse(FeePayment.objects.filter(fee=fee).exists())
        self.assertFalse(
            BusPayment.objects.filter(student=self.student, school=self.school, term_period="T1").exists()
        )
