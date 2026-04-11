"""Teaching scope (attendance + results), management vs teacher rules, and light URL smoke checks."""

from datetime import time
from decimal import Decimal
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from academics.models import ExamType, Result, Subject, Term, Timetable
from accounts.hr_models import StaffPayrollPayment
from accounts.models import User
from schools.models import School
from students.models import SchoolClass, Student


class TeachingScopeAndSmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Scope Test School", subdomain="scope-test-sch-x9")
        cls.subj_math = Subject.objects.create(school=cls.school, name="Mathematics")
        cls.subj_eng = Subject.objects.create(school=cls.school, name="English")
        cls.term = Term.objects.create(school=cls.school, name="Term 1", is_current=True)
        cls.exam = ExamType.objects.create(school=cls.school, name="Test Exam")

        cls.class_a = SchoolClass.objects.create(school=cls.school, name="Form 1A")
        cls.class_b = SchoolClass.objects.create(school=cls.school, name="Form 1B")

        cls.admin = User.objects.create_user(
            username="scope_admin", password="pass12345", school=cls.school, role="school_admin"
        )
        cls.hod = User.objects.create_user(
            username="scope_hod", password="pass12345", school=cls.school, role="hod"
        )
        cls.teacher_homeroom = User.objects.create_user(
            username="scope_th", password="pass12345", school=cls.school, role="teacher"
        )
        cls.class_a.class_teacher = cls.teacher_homeroom
        cls.class_a.save(update_fields=["class_teacher"])

        cls.teacher_tt = User.objects.create_user(
            username="scope_tt", password="pass12345", school=cls.school, role="teacher"
        )
        Timetable.objects.create(
            school=cls.school,
            class_name="Form 1B",
            subject=cls.subj_math,
            teacher=cls.teacher_tt,
            day_of_week="Monday",
            start_time=time(8, 0),
            end_time=time(9, 0),
        )

        su_math = User.objects.create_user(
            username="stu_math", password="pass12345", school=cls.school, role="student"
        )
        su_eng = User.objects.create_user(
            username="stu_eng", password="pass12345", school=cls.school, role="student"
        )
        cls.student_math = Student.objects.create(
            school=cls.school,
            user=su_math,
            admission_number="S001",
            class_name="Form 1B",
        )
        cls.student_eng = Student.objects.create(
            school=cls.school,
            user=su_eng,
            admission_number="S002",
            class_name="Form 1A",
        )
        Result.objects.create(
            student=cls.student_math,
            subject=cls.subj_math,
            exam_type=cls.exam,
            term=cls.term,
            score=80,
            total_score=100,
        )
        Result.objects.create(
            student=cls.student_eng,
            subject=cls.subj_eng,
            exam_type=cls.exam,
            term=cls.term,
            score=70,
            total_score=100,
        )

    def setUp(self):
        self.client = Client()

    def test_hod_attendance_sees_all_classes(self):
        self.client.login(username="scope_hod", password="pass12345")
        r = self.client.get(reverse("operations:attendance_mark"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Form 1A")
        self.assertContains(r, "Form 1B")

    def test_teacher_homeroom_sees_only_homeroom_class(self):
        self.client.login(username="scope_th", password="pass12345")
        r = self.client.get(reverse("operations:attendance_mark"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Form 1A")
        self.assertNotContains(r, ">Form 1B</option>")

    def test_teacher_timetable_sees_only_timetable_class(self):
        self.client.login(username="scope_tt", password="pass12345")
        r = self.client.get(reverse("operations:attendance_mark"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Form 1B")
        self.assertNotContains(r, ">Form 1A</option>")

    def test_results_management_teacher_scoped_to_subjects(self):
        self.client.login(username="scope_tt", password="pass12345")
        r = self.client.get(reverse("academics:results_management"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "stu_math")
        self.assertNotContains(r, "stu_eng")
        self.assertContains(r, "your subjects")

    def test_results_management_admin_sees_all_recent(self):
        self.client.login(username="scope_admin", password="pass12345")
        r = self.client.get(reverse("academics:results_management"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "stu_math")
        self.assertContains(r, "stu_eng")
        self.assertNotContains(r, "your subjects")

    def test_superuser_send_message_requires_privilege(self):
        plain = User.objects.create_user(username="plain_u", password="pass12345", school=self.school, role="teacher")
        self.client.login(username="plain_u", password="pass12345")
        r = self.client.get(reverse("messaging:superuser_send_message"))
        self.assertEqual(r.status_code, 302)

    def test_parent_portal_authenticated_ok(self):
        parent = User.objects.create_user(
            username="scope_parent", password="pass12345", school=self.school, role="parent"
        )
        self.client.login(username="scope_parent", password="pass12345")
        r = self.client.get(reverse("portal"))
        self.assertIn(r.status_code, (200, 302))

    def test_student_results_list_authenticated_ok(self):
        self.client.login(username="stu_math", password="pass12345")
        r = self.client.get(reverse("students:results_list"))
        self.assertEqual(r.status_code, 200)


class StaffPayrollDisburseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Payroll Test School", subdomain="payroll-tst-sch-01")
        cls.accountant = User.objects.create_user(
            username="pay_acct",
            password="pass12345",
            school=cls.school,
            role="accountant",
        )
        cls.teacher = User.objects.create_user(
            username="pay_teacher",
            password="pass12345",
            school=cls.school,
            role="teacher",
        )

    def setUp(self):
        self.client = Client()

    def test_teacher_cannot_open_disburse(self):
        self.client.login(username="pay_teacher", password="pass12345")
        url = reverse("accounts:staff_payroll_disburse", args=[self.teacher.pk])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 302)

    def test_offline_cash_creates_ledger_row(self):
        self.client.login(username="pay_acct", password="pass12345")
        url = reverse("accounts:staff_payroll_disburse", args=[self.teacher.pk])
        r = self.client.post(
            url,
            {
                "disbursement_mode": "offline_cash",
                "period_label": "January 2026",
                "paid_on": "2026-01-15",
                "amount": "500.00",
                "currency": "GHS",
            },
        )
        self.assertEqual(r.status_code, 302)
        p = StaffPayrollPayment.objects.get(user=self.teacher)
        self.assertEqual(p.method, "cash")
        self.assertEqual(p.amount, Decimal("500.00"))
        self.assertEqual(p.paystack_status, "")
        self.assertEqual(p.school, self.school)

    @override_settings(PAYSTACK_SECRET_KEY="sk_test_dummy", PAYSTACK_STAFF_TRANSFERS_ENABLED=True)
    @patch("finance.staff_payroll_paystack.paystack_service.initiate_transfer")
    @patch("finance.staff_payroll_paystack.paystack_service.create_transfer_recipient")
    def test_paystack_momo_queues_transfer(self, mock_recipient, mock_transfer):
        mock_recipient.return_value = {"status": True, "data": {"recipient_code": "RCP_test12345"}}
        mock_transfer.return_value = {
            "status": True,
            "data": {"transfer_code": "TRF_xx1", "message": "Transfer queued"},
        }
        self.teacher.payroll_momo_number = "0244000000"
        self.teacher.payroll_momo_network = "MTN"
        self.teacher.save(
            update_fields=["payroll_momo_number", "payroll_momo_network"]
        )
        self.client.login(username="pay_acct", password="pass12345")
        url = reverse("accounts:staff_payroll_disburse", args=[self.teacher.pk])
        r = self.client.post(
            url,
            {
                "disbursement_mode": "paystack_momo",
                "period_label": "February 2026",
                "paid_on": "2026-02-01",
                "amount": "100.00",
                "currency": "GHS",
            },
        )
        self.assertEqual(r.status_code, 302)
        p = StaffPayrollPayment.objects.get(user=self.teacher, period_label="February 2026")
        self.assertEqual(p.method, "mobile_money")
        self.assertEqual(p.paystack_status, "pending")
        self.assertEqual(p.paystack_transfer_code, "TRF_xx1")
        self.assertTrue(p.reference.startswith("STF"))
        mock_transfer.assert_called_once()
