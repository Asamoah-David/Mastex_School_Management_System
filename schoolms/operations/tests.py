"""Operations workflows: admissions pipeline, etc."""

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from operations.models import AdmissionApplication
from operations.models.canteen import CanteenPayment
from schools.models import School
from students.models import Student


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
