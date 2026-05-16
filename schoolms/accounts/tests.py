"""Teaching scope (attendance + results), management vs teacher rules, and light URL smoke checks."""

import uuid
from datetime import time
from decimal import Decimal
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from academics.models import ExamType, Result, Subject, Term, Timetable
from accounts.hr_models import StaffPayrollPayment
from accounts.models import User
from schools.models import School, SchoolFeature
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
            is_published=True,
        )
        Result.objects.create(
            student=cls.student_eng,
            subject=cls.subj_eng,
            exam_type=cls.exam,
            term=cls.term,
            score=70,
            total_score=100,
            is_published=True,
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

    def test_teacher_two_homerooms_sees_both_classes(self):
        self.class_b.class_teacher = self.teacher_homeroom
        self.class_b.save(update_fields=["class_teacher"])
        self.client.login(username="scope_th", password="pass12345")
        r = self.client.get(reverse("operations:attendance_mark"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, ">Form 1A</option>")
        self.assertContains(r, ">Form 1B</option>")

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
        cls.school_admin = User.objects.create_user(
            username="pay_school_admin",
            password="pass12345",
            school=cls.school,
            role="school_admin",
        )

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.client = Client()

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()

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

    @override_settings(
        PAYSTACK_SECRET_KEY="sk_test_dummy",
        PAYSTACK_STAFF_TRANSFERS_ENABLED=True,
        PAYSTACK_STAFF_SCHOOL_OWNED_PAYOUTS_READY=True,
    )
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
        self.client.login(username="pay_school_admin", password="pass12345")
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

    @override_settings(
        PAYSTACK_SECRET_KEY="sk_test_dummy",
        PAYSTACK_STAFF_TRANSFERS_ENABLED=True,
        PAYSTACK_STAFF_SCHOOL_OWNED_PAYOUTS_READY=True,
    )
    @patch("finance.staff_payroll_paystack.paystack_service.initiate_transfer")
    def test_paystack_blocked_when_school_feature_disabled(self, mock_transfer):
        SchoolFeature.objects.create(
            school=self.school, key="staff_paystack_transfers", enabled=False
        )
        self.teacher.payroll_momo_number = "0244000000"
        self.teacher.payroll_momo_network = "MTN"
        self.teacher.save(update_fields=["payroll_momo_number", "payroll_momo_network"])
        self.client.login(username="pay_school_admin", password="pass12345")
        url = reverse("accounts:staff_payroll_disburse", args=[self.teacher.pk])
        self.client.post(
            url,
            {
                "disbursement_mode": "paystack_momo",
                "period_label": "March 2026",
                "paid_on": "2026-03-01",
                "amount": "50.00",
                "currency": "GHS",
            },
        )
        mock_transfer.assert_not_called()
        self.assertFalse(
            StaffPayrollPayment.objects.filter(
                user=self.teacher, period_label="March 2026"
            ).exists()
        )

    @override_settings(
        PAYSTACK_SECRET_KEY="sk_test_dummy",
        PAYSTACK_STAFF_TRANSFERS_ENABLED=True,
        PAYSTACK_STAFF_SCHOOL_OWNED_PAYOUTS_READY=True,
    )
    @patch("finance.staff_payroll_paystack.paystack_service.initiate_transfer")
    def test_paystack_blocked_for_non_leadership_user(self, mock_transfer):
        self.teacher.payroll_momo_number = "0244000000"
        self.teacher.payroll_momo_network = "MTN"
        self.teacher.save(update_fields=["payroll_momo_number", "payroll_momo_network"])
        self.client.login(username="pay_acct", password="pass12345")
        url = reverse("accounts:staff_payroll_disburse", args=[self.teacher.pk])
        self.client.post(
            url,
            {
                "disbursement_mode": "paystack_momo",
                "period_label": "April 2026",
                "paid_on": "2026-04-01",
                "amount": "50.00",
                "currency": "GHS",
            },
        )
        mock_transfer.assert_not_called()
        self.assertFalse(
            StaffPayrollPayment.objects.filter(
                user=self.teacher, period_label="April 2026"
            ).exists()
        )

    @override_settings(
        PAYSTACK_SECRET_KEY="sk_test_dummy",
        PAYSTACK_STAFF_TRANSFERS_ENABLED=True,
        PAYSTACK_STAFF_SCHOOL_OWNED_PAYOUTS_READY=False,
    )
    @patch("finance.staff_payroll_paystack.paystack_service.initiate_transfer")
    def test_paystack_blocked_when_school_owned_controls_not_ready(self, mock_transfer):
        self.teacher.payroll_momo_number = "0244000000"
        self.teacher.payroll_momo_network = "MTN"
        self.teacher.save(update_fields=["payroll_momo_number", "payroll_momo_network"])
        self.client.login(username="pay_school_admin", password="pass12345")
        url = reverse("accounts:staff_payroll_disburse", args=[self.teacher.pk])
        self.client.post(
            url,
            {
                "disbursement_mode": "paystack_momo",
                "period_label": "May 2026",
                "paid_on": "2026-05-01",
                "amount": "50.00",
                "currency": "GHS",
            },
        )
        mock_transfer.assert_not_called()
        self.assertFalse(
            StaffPayrollPayment.objects.filter(
                user=self.teacher, period_label="May 2026"
            ).exists()
        )


class StaffPayrollBulkAndPayslipTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Bulk PS School", subdomain="bulk-ps-sch-01")
        SchoolFeature.objects.update_or_create(
            school=cls.school, key="staff_management", defaults={"enabled": True}
        )
        cls.accountant = User.objects.create_user(
            username="bulk_acct",
            password="pass12345",
            school=cls.school,
            role="accountant",
        )
        cls.teacher_a = User.objects.create_user(
            username="bulk_ta",
            password="pass12345",
            school=cls.school,
            role="teacher",
        )
        cls.teacher_b = User.objects.create_user(
            username="bulk_tb",
            password="pass12345",
            school=cls.school,
            role="teacher",
        )

    def setUp(self):
        self.client = Client()
        from django.core.cache import cache

        SchoolFeature.objects.update_or_create(
            school=self.school, key="staff_management", defaults={"enabled": True}
        )
        cache.delete(School._feature_cache_key(self.school.pk))

    def test_bulk_record_creates_lines(self):
        self.client.login(username="bulk_acct", password="pass12345")
        url = reverse("accounts:staff_payroll_bulk_record")
        r = self.client.post(
            url,
            {
                "staff_ids": [str(self.teacher_a.pk), str(self.teacher_b.pk)],
                "period_label": "April 2026",
                "paid_on": "2026-04-01",
                "default_amount": "300.00",
                "currency": "GHS",
                "method": "cash",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(
            StaffPayrollPayment.objects.filter(
                school=self.school, period_label="April 2026"
            ).count(),
            2,
        )

    def test_staff_can_open_own_payslip(self):
        pay = StaffPayrollPayment.objects.create(
            school=self.school,
            user=self.teacher_a,
            period_label="May 2026",
            amount=Decimal("100.00"),
            currency="GHS",
            paid_on="2026-05-01",
            method="bank",
            recorded_by=self.accountant,
        )
        self.client.login(username="bulk_ta", password="pass12345")
        r = self.client.get(
            reverse("accounts:staff_payroll_payslip", args=[pay.pk])
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "May 2026")

    def test_staff_cannot_open_others_payslip(self):
        pay = StaffPayrollPayment.objects.create(
            school=self.school,
            user=self.teacher_a,
            period_label="June 2026",
            amount=Decimal("100.00"),
            currency="GHS",
            paid_on="2026-06-01",
            method="bank",
            recorded_by=self.accountant,
        )
        self.client.login(username="bulk_tb", password="pass12345")
        r = self.client.get(
            reverse("accounts:staff_payroll_payslip", args=[pay.pk])
        )
        self.assertEqual(r.status_code, 302)


class TimetableOverlapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="TT School", subdomain="tt-sch-ov-01")
        cls.subj_a = Subject.objects.create(school=cls.school, name="Math")
        cls.subj_b = Subject.objects.create(school=cls.school, name="English")
        cls.admin = User.objects.create_user(
            username="tt_admin",
            password="pass12345",
            school=cls.school,
            role="school_admin",
        )

    def setUp(self):
        self.client = Client()

    def test_rejects_overlapping_class_slot(self):
        self.client.login(username="tt_admin", password="pass12345")
        url = reverse("academics:timetable_create")
        base = {
            "class_name": "JHS 1A",
            "day": "Monday",
            "start_time": "08:00",
            "end_time": "09:00",
        }
        r1 = self.client.post(
            url,
            {**base, "subject": str(self.subj_a.pk)},
        )
        self.assertEqual(r1.status_code, 302)
        r2 = self.client.post(
            url,
            {
                "class_name": "JHS 1A",
                "day": "Monday",
                "start_time": "08:30",
                "end_time": "09:30",
                "subject": str(self.subj_b.pk),
            },
        )
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(
            Timetable.objects.filter(school=self.school, class_name="JHS 1A").count(),
            1,
        )


class PeopleAccountsFeatureGateTests(TestCase):
    """People / accounts views respect staff_management and student_enrollment flags."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="People Gate School", subdomain=f"ppl-gate-{uuid.uuid4().hex[:10]}")
        for key in ("staff_management", "student_enrollment", "leave_management"):
            SchoolFeature.objects.update_or_create(
                school=cls.school, key=key, defaults={"enabled": True}
            )
        cls.admin = User.objects.create_user(
            username="ppl_gate_admin",
            password="pw12345",
            school=cls.school,
            role="school_admin",
        )

    def setUp(self):
        self.client = Client()
        for key in ("staff_management", "student_enrollment", "leave_management"):
            SchoolFeature.objects.update_or_create(
                school=self.school, key=key, defaults={"enabled": True}
            )

    def test_staff_list_redirects_when_staff_management_disabled(self):
        """Non-leadership staff with directory access are gated; heads bypass (see staff_list docstring)."""
        SchoolFeature.objects.update_or_create(
            school=self.school, key="staff_management", defaults={"enabled": False}
        )
        User.objects.create_user(
            username="ppl_gate_teacher",
            password="pw12345",
            school=self.school,
            role="teacher",
        )
        self.client.login(username="ppl_gate_teacher", password="pw12345")
        r = self.client.get(reverse("accounts:staff_list"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)

    def test_parent_list_accessible_to_leadership_when_student_enrollment_disabled(self):
        """Parent list is leadership-only; enrollment flag does not lock out head/deputy/HOD."""
        SchoolFeature.objects.update_or_create(
            school=self.school, key="student_enrollment", defaults={"enabled": False}
        )
        self.client.login(username="ppl_gate_admin", password="pw12345")
        r = self.client.get(reverse("accounts:parent_list"))
        self.assertEqual(r.status_code, 200)

    def test_user_management_redirects_when_both_people_modules_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="staff_management", defaults={"enabled": False}
        )
        SchoolFeature.objects.update_or_create(
            school=self.school, key="student_enrollment", defaults={"enabled": False}
        )
        self.client.login(username="ppl_gate_admin", password="pw12345")
        r = self.client.get(reverse("accounts:user_management"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)

    def test_leave_policy_list_redirects_when_leave_management_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="leave_management", defaults={"enabled": False}
        )
        self.client.login(username="ppl_gate_admin", password="pw12345")
        r = self.client.get(reverse("accounts:leave_policy_list"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)

    def test_admin_reset_requests_redirects_when_both_people_modules_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="staff_management", defaults={"enabled": False}
        )
        SchoolFeature.objects.update_or_create(
            school=self.school, key="student_enrollment", defaults={"enabled": False}
        )
        self.client.login(username="ppl_gate_admin", password="pw12345")
        r = self.client.get(reverse("accounts:admin_reset_requests"))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)


class ApiCheckIdentifierTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="API ID School", subdomain="api-id-sch-1")
        cls.admin = User.objects.create_user(
            username="api_id_admin",
            email="admin@apiid.test",
            password="pw12345",
            school=cls.school,
            role="school_admin",
        )

    def setUp(self):
        self.client = Client()
        self.url = reverse("accounts:api_check_identifier")

    def test_anonymous_username_taken(self):
        r = self.client.get(self.url, {"kind": "username", "value": "api_id_admin"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertFalse(data["available"])

    def test_anonymous_username_available(self):
        r = self.client.get(self.url, {"kind": "username", "value": "totally_unused_xyz_99"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["available"])

    def test_admission_number_requires_login(self):
        r = self.client.get(self.url, {"kind": "admission_number", "value": "ADM001"})
        self.assertEqual(r.status_code, 403)

    def test_admission_number_scoped_to_school(self):
        st = Student.objects.create(
            school=self.school,
            user=User.objects.create_user(
                username="stu_adm1", password="pw12345", school=self.school, role="student"
            ),
            admission_number="ADM-SCOPE-1",
            class_name="Form 1A",
        )
        self.client.login(username="api_id_admin", password="pw12345")
        r = self.client.get(self.url, {"kind": "admission_number", "value": "ADM-SCOPE-1"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["available"])
        r_same = self.client.get(
            self.url,
            {
                "kind": "admission_number",
                "value": "ADM-SCOPE-1",
                "exclude_student": str(st.pk),
            },
        )
        self.assertTrue(r_same.json()["available"])
        r2 = self.client.get(self.url, {"kind": "admission_number", "value": "ADM-NEW-999"})
        self.assertTrue(r2.json()["available"])

    def test_email_exclude_current_user(self):
        self.client.login(username="api_id_admin", password="pw12345")
        r = self.client.get(
            self.url,
            {"kind": "email", "value": "admin@apiid.test", "exclude": str(self.admin.pk)},
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["available"])

    @override_settings(API_IDENTIFIER_CHECK_PER_MINUTE=5)
    def test_identifier_check_rate_limit(self):
        from django.core.cache import cache

        cache.clear()
        for i in range(5):
            r = self.client.get(self.url, {"kind": "username", "value": f"probe_{i}_xyz"})
            self.assertEqual(r.status_code, 200, msg=f"iteration {i}")
        r6 = self.client.get(self.url, {"kind": "username", "value": "probe_6_xyz"})
        self.assertEqual(r6.status_code, 429)
        self.assertIn("Too many", r6.json().get("error", ""))


class TwoFaNextSanitizationTests(TestCase):
    """Open-redirect hardening for post-login 2FA flows."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="2FA Next Sch", subdomain="2fa-next-sch-1")
        cls.user = User.objects.create_user(
            username="twofa_next_user",
            password="pw12345",
            school=cls.school,
            role="teacher",
        )

    def setUp(self):
        self.client = Client()

    def test_challenge_page_sanitizes_external_next_query(self):
        import time as _time
        from accounts.totp_views import SESSION_KEY_2FA_USER, SESSION_KEY_2FA_TS

        s = self.client.session
        s[SESSION_KEY_2FA_USER] = self.user.pk
        s[SESSION_KEY_2FA_TS] = _time.time()
        s.save()
        r = self.client.get(
            reverse("accounts:2fa_challenge") + "?next=https://evil.example/phish",
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'name="next"')
        self.assertNotContains(r, "evil.example")
        self.assertContains(r, 'value="/"')

    def test_login_redirect_to_challenge_strips_external_next(self):
        u = User.objects.create_user(
            username="twofa_enabled_u",
            password="pw12345",
            school=self.school,
            role="teacher",
        )
        u.totp_enabled = True
        u.save(update_fields=["totp_enabled"])
        r = self.client.post(
            reverse("accounts:login") + "?next=https://evil.example/phish",
            {"username": "twofa_enabled_u", "password": "pw12345"},
            follow=False,
        )
        self.assertEqual(r.status_code, 302)
        loc = r["Location"]
        self.assertIn("/accounts/2fa/challenge/", loc)
        self.assertNotIn("evil", loc)
        self.assertIn("next=%2F", loc)


class StaffManagementLeadershipBypassTests(TestCase):
    """Head / deputy / HOD can open staff profiles when the staff_management flag is off."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Bypass Sch", subdomain="bypass-sch-1")
        cls.head = User.objects.create_user(
            username="bypass_head", password="pw12345", school=cls.school, role="school_admin"
        )
        cls.teacher = User.objects.create_user(
            username="bypass_teacher", password="pw12345", school=cls.school, role="teacher"
        )

    def setUp(self):
        self.client = Client()
        SchoolFeature.objects.update_or_create(
            school=self.school, key="staff_management", defaults={"enabled": False}
        )

    def test_teacher_redirected_from_staff_detail_when_feature_off(self):
        self.client.login(username="bypass_teacher", password="pw12345")
        r = self.client.get(reverse("accounts:staff_detail", args=[self.head.pk]))
        self.assertRedirects(r, reverse("accounts:school_dashboard"), fetch_redirect_response=False)

    def test_school_admin_reaches_staff_detail_when_feature_off(self):
        self.client.login(username="bypass_head", password="pw12345")
        r = self.client.get(reverse("accounts:staff_detail", args=[self.teacher.pk]))
        self.assertEqual(r.status_code, 200)


class StudentEnrollmentLeadershipBypassTests(TestCase):
    """School leadership can manage parents when student_enrollment is disabled."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Enroll Bypass Sch", subdomain="enroll-bypass-sch-1")
        cls.head = User.objects.create_user(
            username="enroll_bypass_head", password="pw12345", school=cls.school, role="school_admin"
        )

    def setUp(self):
        self.client = Client()
        SchoolFeature.objects.update_or_create(
            school=self.school, key="student_enrollment", defaults={"enabled": False}
        )

    def test_school_admin_reaches_parent_list_when_enrollment_feature_off(self):
        self.client.login(username="enroll_bypass_head", password="pw12345")
        r = self.client.get(reverse("accounts:parent_list"))
        self.assertEqual(r.status_code, 200)
