"""Paystack gross-up (pass processing estimate to payer)."""

from decimal import Decimal

from django.test import SimpleTestCase, override_settings

from finance.paystack_service import compute_paystack_gross_from_net

from django.test import Client, TestCase
from django.urls import reverse
from unittest.mock import patch
import uuid

from finance.models import PaymentTransaction, Fee, FeePayment, FeeInstallmentPlan, FeeStructure
from schools.models import School, SchoolFeature
from accounts.models import User
from students.models import Student
from payments.services.ledger import PaymentTypes, record_payment_transaction
from audit.models import AuditLog


class PaystackGrossUpTests(SimpleTestCase):
    @override_settings(PAYSTACK_PASS_FEE_TO_PAYER=True, PAYSTACK_PROCESSING_FEE_PERCENT=1.95)
    def test_gross_not_less_than_net(self):
        net, gross = compute_paystack_gross_from_net(Decimal("100.00"))
        self.assertEqual(net, Decimal("100.00"))
        self.assertGreaterEqual(gross, net)

    @override_settings(PAYSTACK_PASS_FEE_TO_PAYER=True, PAYSTACK_PROCESSING_FEE_PERCENT=1.95)
    def test_gross_rounds_up(self):
        net, gross = compute_paystack_gross_from_net(Decimal("100.00"))
        # 100 / (1 - 0.0195) ≈ 101.99; rounded up to 2dp
        self.assertEqual(gross, Decimal("101.99"))

    @override_settings(PAYSTACK_PASS_FEE_TO_PAYER=False)
    def test_disabled_equals_net(self):
        net, gross = compute_paystack_gross_from_net(Decimal("50.00"))
        self.assertEqual(net, Decimal("50.00"))
        self.assertEqual(gross, Decimal("50.00"))


class LedgerWriterAndViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.s1 = School.objects.create(name="Ledger School 1", subdomain="ledg-sch-01")
        cls.s2 = School.objects.create(name="Ledger School 2", subdomain="ledg-sch-02")
        cls.admin1 = User.objects.create_user(
            username="ledger_admin1",
            password="pw12345",
            school=cls.s1,
            role="school_admin",
        )
        cls.admin2 = User.objects.create_user(
            username="ledger_admin2",
            password="pw12345",
            school=cls.s2,
            role="school_admin",
        )
        cls.superuser = User.objects.create_superuser(
            username="ledger_su",
            password="pw12345",
            email="su@example.com",
        )

        PaymentTransaction.objects.create(
            school=cls.s1,
            provider="paystack",
            reference="REF_S1_OK",
            amount=Decimal("10.00"),
            currency="GHS",
            status="completed",
            payment_type=PaymentTypes.SCHOOL_FEE,
            object_id="1",
        )
        PaymentTransaction.objects.create(
            school=cls.s2,
            provider="paystack",
            reference="REF_S2_OK",
            amount=Decimal("12.00"),
            currency="GHS",
            status="completed",
            payment_type=PaymentTypes.SCHOOL_FEE,
            object_id="2",
        )

        cls.tx_s1_failed = PaymentTransaction.objects.create(
            school=cls.s1,
            provider="paystack",
            reference="REF_S1_FAIL",
            amount=Decimal("5.00"),
            currency="GHS",
            status="failed",
            payment_type=PaymentTypes.SCHOOL_FEE,
            object_id="3",
        )

    def setUp(self):
        self.client = Client()

    def test_record_payment_transaction_normalizes_status_provider_and_type(self):
        record_payment_transaction(
            provider=" Offline ",
            reference="REF_NORM_01",
            school_id=self.s1.id,
            amount=Decimal("1.00"),
            status="Completed",
            payment_type="fee",
            object_id="x",
            metadata={"fee_id": 1},
        )
        tx = PaymentTransaction.objects.get(reference="REF_NORM_01")
        self.assertEqual(tx.provider, "offline")
        self.assertEqual(tx.status, "completed")
        self.assertEqual(tx.payment_type, PaymentTypes.SCHOOL_FEE)

    def test_ledger_list_scoped_to_school(self):
        self.client.login(username="ledger_admin1", password="pw12345")
        r = self.client.get(reverse("finance:payment_ledger_list"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "REF_S1_OK")
        self.assertNotContains(r, "REF_S2_OK")

    def test_ledger_export_scoped_to_school(self):
        self.client.login(username="ledger_admin1", password="pw12345")
        r = self.client.get(reverse("finance:payment_ledger_export_csv"))
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8")
        self.assertIn("REF_S1_OK", body)
        self.assertNotIn("REF_S2_OK", body)

    def test_superuser_sees_all_schools(self):
        self.client.login(username="ledger_su", password="pw12345")
        r = self.client.get(reverse("finance:payment_ledger_list"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "REF_S1_OK")
        self.assertContains(r, "REF_S2_OK")

    def test_bulk_review_selected_is_school_scoped(self):
        self.client.login(username="ledger_admin1", password="pw12345")
        url = reverse("finance:payment_ledger_bulk_review")
        tx_other = PaymentTransaction.objects.get(reference="REF_S2_OK")
        before = AuditLog.objects.count()
        resp = self.client.post(
            url,
            data={"review": "reviewed", "scope": "selected", "ids": [str(self.tx_s1_failed.id), str(tx_other.id)]},
        )
        self.assertEqual(resp.status_code, 302)
        self.tx_s1_failed.refresh_from_db()
        tx_other.refresh_from_db()
        self.assertEqual(self.tx_s1_failed.review_status, "reviewed")
        self.assertEqual(tx_other.review_status, "open")
        self.assertGreaterEqual(AuditLog.objects.count(), before + 1)

    def test_bulk_review_all_filtered_only_updates_filtered_rows(self):
        self.client.login(username="ledger_admin1", password="pw12345")
        url = reverse("finance:payment_ledger_bulk_review")
        before = AuditLog.objects.count()
        resp = self.client.post(
            f"{url}?status=failed",
            data={"review": "reviewed", "scope": "all", "confirm_all": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        self.tx_s1_failed.refresh_from_db()
        ok = PaymentTransaction.objects.get(reference="REF_S1_OK")
        self.assertEqual(self.tx_s1_failed.review_status, "reviewed")
        self.assertEqual(ok.review_status, "open")
        self.assertGreaterEqual(AuditLog.objects.count(), before + 1)

    def test_bulk_review_enforce_queue_limits_to_open_pending_failed(self):
        self.client.login(username="ledger_admin1", password="pw12345")
        # Create a completed tx in same school that should not be touched by enforce_queue
        completed = PaymentTransaction.objects.get(reference="REF_S1_OK")
        url = reverse("finance:payment_ledger_bulk_review")
        resp = self.client.post(
            f"{url}?status_any=pending,failed",
            data={"review": "reviewed", "scope": "all", "confirm_all": "1", "enforce_queue": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        self.tx_s1_failed.refresh_from_db()
        completed.refresh_from_db()
        self.assertEqual(self.tx_s1_failed.review_status, "reviewed")
        self.assertEqual(completed.review_status, "open")

    def test_bulk_review_all_requires_confirmation(self):
        self.client.login(username="ledger_admin1", password="pw12345")
        url = reverse("finance:payment_ledger_bulk_review")
        resp = self.client.post(f"{url}?status=failed", data={"review": "reviewed", "scope": "all"})
        self.assertEqual(resp.status_code, 302)
        self.tx_s1_failed.refresh_from_db()
        self.assertEqual(self.tx_s1_failed.review_status, "open")

    def test_bulk_review_redirects_back_to_referer(self):
        self.client.login(username="ledger_admin1", password="pw12345")
        url = reverse("finance:payment_ledger_bulk_review")
        nxt = reverse("finance:payment_ledger_queue_page")
        resp = self.client.post(
            f"{url}?status=failed",
            data={"review": "reviewed", "scope": "all", "confirm_all": "1", "next": nxt},
            HTTP_REFERER=nxt,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, nxt)

    def test_superuser_can_render_health_without_school_attached(self):
        self.client.login(username="ledger_su", password="pw12345")
        r = self.client.get(reverse("finance:payment_ledger_health"))
        self.assertEqual(r.status_code, 200)

    def test_export_writes_audit_log(self):
        self.client.login(username="ledger_admin1", password="pw12345")
        before = AuditLog.objects.count()
        r = self.client.get(reverse("finance:payment_ledger_export_csv"))
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(AuditLog.objects.count(), before + 1)

    def test_reconciliation_queue_redirects_to_ledger_with_defaults(self):
        self.client.login(username="ledger_admin1", password="pw12345")
        r = self.client.get(reverse("finance:payment_ledger_queue"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("review=open", r.url)
        self.assertIn("from=", r.url)
        self.assertIn("to=", r.url)
        self.assertIn("status_any=pending%2Cfailed", r.url)

        r2 = self.client.get(reverse("finance:payment_ledger_queue") + "?queue=failed")
        self.assertEqual(r2.status_code, 302)
        self.assertIn("status=failed", r2.url)

    def test_status_any_filters_list_and_export(self):
        self.client.login(username="ledger_admin1", password="pw12345")
        r = self.client.get(reverse("finance:payment_ledger_list") + "?status_any=pending,failed")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "REF_S1_FAIL")
        self.assertNotContains(r, "REF_S1_OK")

        e = self.client.get(reverse("finance:payment_ledger_export_csv") + "?status_any=pending,failed")
        self.assertEqual(e.status_code, 200)
        body = e.content.decode("utf-8")
        self.assertIn("REF_S1_FAIL", body)
        self.assertNotIn("REF_S1_OK", body)

    def test_queue_page_renders(self):
        self.client.login(username="ledger_admin1", password="pw12345")
        r = self.client.get(reverse("finance:payment_ledger_queue_page"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Reconciliation queue")
        self.assertContains(r, "Export queue CSV")
        self.assertContains(r, "Days")
        self.assertContains(r, "Open pending")
        self.assertContains(r, "Open failed")

    def test_queue_export_enforces_open_pending_failed(self):
        self.client.login(username="ledger_admin1", password="pw12345")
        r = self.client.get(reverse("finance:payment_ledger_queue_export_csv"))
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8")
        self.assertIn("REF_S1_FAIL", body)
        self.assertNotIn("REF_S1_OK", body)

    def test_bulk_preview_endpoint(self):
        self.client.login(username="ledger_admin1", password="pw12345")
        url = reverse("finance:payment_ledger_bulk_review_preview")
        r = self.client.get(url + "?status_any=pending,failed&enforce_queue=1")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("count", data)


class CheckPaymentStatusScopeTests(TestCase):
    """Reference lookup must not leak across tenants."""

    @classmethod
    def setUpTestData(cls):
        cls.s1 = School.objects.create(name="CPS School A", subdomain="cps-a")
        cls.s2 = School.objects.create(name="CPS School B", subdomain="cps-b")
        cls.admin_s1 = User.objects.create_user(
            username="cps_admin_s1",
            password="pw12345",
            school=cls.s1,
            role="school_admin",
        )
        cls.stu_user_b = User.objects.create_user(
            username="cps_stu_b",
            password="pw12345",
            role="student",
        )
        cls.stu_b = Student.objects.create(
            school=cls.s2,
            user=cls.stu_user_b,
            admission_number="ADM-B-1",
            class_name="1A",
        )
        cls.fee_b = Fee.objects.create(
            school=cls.s2,
            student=cls.stu_b,
            amount=Decimal("100.00"),
            amount_paid=Decimal("0"),
            paystack_reference="REF_SECRET_OTHER_SCHOOL",
        )
        FeePayment.objects.create(
            fee=cls.fee_b,
            amount=Decimal("10.00"),
            paystack_reference="REF_SECRET_OTHER_SCHOOL",
            status="completed",
            school=cls.s2,
        )

    def setUp(self):
        self.client = Client()

    def test_school_staff_cannot_resolve_other_school_reference(self):
        self.client.login(username="cps_admin_s1", password="pw12345")
        url = reverse("finance:check_payment_status")
        r = self.client.post(url, {"reference": "REF_SECRET_OTHER_SCHOOL"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "No payment found")

    def test_superuser_can_resolve_any_reference(self):
        su = User.objects.create_superuser(
            username="cps_su",
            email="cps_su@example.com",
            password="pw12345",
        )
        self.client.login(username="cps_su", password="pw12345")
        url = reverse("finance:check_payment_status")
        r = self.client.post(url, {"reference": "REF_SECRET_OTHER_SCHOOL"})
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "No payment found")


# ---------------------------------------------------------------------------
#  School Funds Ledger — Phase 2 tests
# ---------------------------------------------------------------------------

class SchoolFundsLedgerTests(TestCase):
    """Tests for finance.services.school_funds service layer."""

    @classmethod
    def setUpTestData(cls):
        cls.school_a = School.objects.create(name="Funds School A", subdomain="funds-a")
        cls.school_b = School.objects.create(name="Funds School B", subdomain="funds-b")

    def test_record_fee_collected_creates_entries_and_updates_balance(self):
        from finance.services.school_funds import record_fee_collected, get_balance
        from finance.models import SchoolFundsLedgerEntry

        record_fee_collected(
            school_id=self.school_a.pk,
            amount=Decimal("100.00"),
            reference="REF_LEDGER_001",
        )
        bal = get_balance(self.school_a.pk)
        self.assertEqual(bal["collected_total"], Decimal("100.00"))
        self.assertEqual(bal["available_total"], Decimal("100.00"))

        entries = SchoolFundsLedgerEntry.objects.filter(
            school=self.school_a, reference="REF_LEDGER_001"
        )
        self.assertEqual(entries.count(), 2)
        states = set(entries.values_list("state", flat=True))
        self.assertEqual(states, {"collected", "available"})

    def test_reserve_funds_succeeds_when_sufficient(self):
        from finance.services.school_funds import record_fee_collected, reserve_funds, get_balance

        record_fee_collected(
            school_id=self.school_a.pk,
            amount=Decimal("200.00"),
            reference="REF_LEDGER_002",
        )
        ok = reserve_funds(
            school_id=self.school_a.pk,
            amount=Decimal("150.00"),
            reference="PAYOUT_001",
        )
        self.assertTrue(ok)
        bal = get_balance(self.school_a.pk)
        self.assertEqual(bal["available_total"], Decimal("50.00"))
        self.assertEqual(bal["reserved_total"], Decimal("150.00"))

    def test_reserve_funds_fails_when_insufficient(self):
        from finance.services.school_funds import record_fee_collected, reserve_funds, get_balance

        record_fee_collected(
            school_id=self.school_b.pk,
            amount=Decimal("50.00"),
            reference="REF_LEDGER_003",
        )
        ok = reserve_funds(
            school_id=self.school_b.pk,
            amount=Decimal("100.00"),
            reference="PAYOUT_002",
        )
        self.assertFalse(ok)
        bal = get_balance(self.school_b.pk)
        self.assertEqual(bal["available_total"], Decimal("50.00"))
        self.assertEqual(bal["reserved_total"], Decimal("0"))

    def test_release_reserved_funds(self):
        from finance.services.school_funds import (
            record_fee_collected, reserve_funds,
            release_reserved_funds, get_balance,
        )

        record_fee_collected(school_id=self.school_a.pk, amount=Decimal("300.00"), reference="REF_LEDGER_004")
        reserve_funds(school_id=self.school_a.pk, amount=Decimal("100.00"), reference="PAYOUT_003")
        release_reserved_funds(school_id=self.school_a.pk, amount=Decimal("100.00"), reference="PAYOUT_003_CANCEL")

        bal = get_balance(self.school_a.pk)
        self.assertEqual(bal["reserved_total"], Decimal("0"))

    def test_mark_funds_paid_out(self):
        from finance.services.school_funds import (
            record_fee_collected, reserve_funds,
            mark_funds_paid_out, get_balance,
        )

        record_fee_collected(school_id=self.school_b.pk, amount=Decimal("500.00"), reference="REF_LEDGER_005")
        reserve_funds(school_id=self.school_b.pk, amount=Decimal("200.00"), reference="PAYOUT_004")
        mark_funds_paid_out(school_id=self.school_b.pk, amount=Decimal("200.00"), reference="PAYOUT_004_EXEC")

        bal = get_balance(self.school_b.pk)
        self.assertEqual(bal["reserved_total"], Decimal("0"))
        self.assertEqual(bal["paid_out_total"], Decimal("200.00"))
        self.assertEqual(bal["available_total"], Decimal("300.00"))

    def test_cross_school_isolation(self):
        from finance.services.school_funds import record_fee_collected, get_balance

        record_fee_collected(school_id=self.school_a.pk, amount=Decimal("1000.00"), reference="REF_ISO_A")
        record_fee_collected(school_id=self.school_b.pk, amount=Decimal("50.00"), reference="REF_ISO_B")

        bal_a = get_balance(self.school_a.pk)
        bal_b = get_balance(self.school_b.pk)

        # Each school has only its own funds
        self.assertGreaterEqual(bal_a["collected_total"], Decimal("1000.00"))
        self.assertLessEqual(bal_b["collected_total"], Decimal("550.00"))  # school_b's total across all tests

    def test_zero_amount_is_ignored(self):
        from finance.services.school_funds import record_fee_collected, get_balance
        from finance.models import SchoolFundsLedgerEntry

        before = SchoolFundsLedgerEntry.objects.filter(school=self.school_a).count()
        record_fee_collected(school_id=self.school_a.pk, amount=Decimal("0"), reference="REF_ZERO")
        after = SchoolFundsLedgerEntry.objects.filter(school=self.school_a).count()
        self.assertEqual(before, after)

    def test_negative_amount_is_ignored(self):
        from finance.services.school_funds import record_fee_collected
        from finance.models import SchoolFundsLedgerEntry

        before = SchoolFundsLedgerEntry.objects.filter(school=self.school_a).count()
        record_fee_collected(school_id=self.school_a.pk, amount=Decimal("-10"), reference="REF_NEG")
        after = SchoolFundsLedgerEntry.objects.filter(school=self.school_a).count()
        self.assertEqual(before, after)

    def test_ledger_entry_is_append_only(self):
        from finance.services.school_funds import record_fee_collected
        from finance.models import SchoolFundsLedgerEntry

        record_fee_collected(school_id=self.school_a.pk, amount=Decimal("10"), reference="REF_APPEND")
        entry = SchoolFundsLedgerEntry.objects.filter(reference="REF_APPEND").first()
        self.assertIsNotNone(entry)

        with self.assertRaises(ValueError):
            entry.description = "tampered"
            entry.save()

        with self.assertRaises(ValueError):
            entry.delete()

    def test_rebuild_balance_from_ledger(self):
        from finance.services.school_funds import (
            record_fee_collected, reserve_funds,
            rebuild_balance_from_ledger, get_balance,
        )

        record_fee_collected(school_id=self.school_a.pk, amount=Decimal("400.00"), reference="REF_REBUILD_1")
        reserve_funds(school_id=self.school_a.pk, amount=Decimal("50.00"), reference="REF_REBUILD_RES")

        totals = rebuild_balance_from_ledger(self.school_a.pk)
        bal = get_balance(self.school_a.pk)

        # After rebuild, balance should reflect all entries from all tests for school_a
        self.assertGreaterEqual(bal["collected_total"], Decimal("400.00"))
        self.assertIsNotNone(bal["last_reconciled_at"])


class PaymentVoidWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Void School", subdomain="void-school")
        cls.admin = User.objects.create_user(
            username="void_admin",
            password="pw12345",
            school=cls.school,
            role="school_admin",
        )
        cls.student_user = User.objects.create_user(
            username="void_student_user",
            password="pw12345",
            school=cls.school,
            role="student",
        )
        cls.student = Student.objects.create(
            school=cls.school,
            user=cls.student_user,
            admission_number="VOID-001",
            class_name="JHS 1",
        )
        cls.fee = Fee.objects.create(
            school=cls.school,
            student=cls.student,
            amount=Decimal("100.00"),
            amount_paid=Decimal("100.00"),
            paid=True,
        )
        cls.payment = FeePayment.objects.create(
            fee=cls.fee,
            school=cls.school,
            amount=Decimal("100.00"),
            status="completed",
            paystack_reference="REF_VOID_001",
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username="void_admin", password="pw12345")
        self.payment = FeePayment.objects.get(pk=self.__class__.payment.pk)
        self.fee = Fee.objects.get(pk=self.__class__.fee.pk)

    @patch("finance.views.paystack_service.initiate_refund")
    def test_void_paystack_payment_queues_refund_without_reversing_fee(self, refund_mock):
        """B4-B phase 1: refund API accepted → row stays completed until webhook."""
        refund_mock.return_value = {"status": True, "message": "ok"}
        resp = self.client.post(
            reverse("finance:payment_history_void", kwargs={"pk": self.payment.pk}),
            data={"void_reason": "Duplicate receipt posted in error."},
        )
        self.assertEqual(resp.status_code, 302)
        self.payment.refresh_from_db()
        self.fee.refresh_from_db()
        self.assertEqual(self.payment.refund_status, FeePayment.REFUND_STATUS_REQUESTED)
        self.assertEqual(self.payment.status, "completed")
        self.assertIsNone(self.payment.voided_at)
        self.assertEqual(self.fee.amount_paid, Decimal("100.00"))

    def test_void_offline_payment_reverses_immediately(self):
        """No Paystack reference → synchronous void (legacy behaviour)."""
        self.payment.paystack_reference = ""
        self.payment.save(update_fields=["paystack_reference"])
        resp = self.client.post(
            reverse("finance:payment_history_void", kwargs={"pk": self.payment.pk}),
            data={"void_reason": "Cash deposit was recorded twice by mistake."},
        )
        self.assertEqual(resp.status_code, 302)
        self.payment.refresh_from_db()
        self.fee.refresh_from_db()
        self.assertEqual(self.payment.status, "failed")
        self.assertIsNotNone(self.payment.voided_at)
        self.assertEqual(self.fee.amount_paid, Decimal("0.00"))
        self.assertFalse(self.fee.paid)

    def test_refund_processed_webhook_reverses_fee_balance(self):
        """B4-B phase 2: Paystack confirms refund → fee balance reversed."""
        from finance.views import _paystack_webhook_fee_refund

        self.payment.refund_status = FeePayment.REFUND_STATUS_REQUESTED
        self.payment.void_reason = "test"
        self.payment.voided_by = self.admin
        self.payment.save(update_fields=["refund_status", "void_reason", "voided_by"])

        _paystack_webhook_fee_refund(
            {"data": {"transaction": {"reference": "REF_VOID_001"}}},
            "refund.processed",
        )
        self.payment.refresh_from_db()
        self.fee.refresh_from_db()
        self.assertEqual(self.payment.refund_status, FeePayment.REFUND_STATUS_PROCESSED)
        self.assertEqual(self.payment.status, "failed")
        self.assertIsNotNone(self.payment.voided_at)
        self.assertEqual(self.fee.amount_paid, Decimal("0.00"))

    @patch("finance.views.paystack_service.initiate_refund")
    def test_void_aborts_when_refund_fails(self, refund_mock):
        refund_mock.return_value = {"status": False, "message": "gateway timeout"}
        resp = self.client.post(
            reverse("finance:payment_history_void", kwargs={"pk": self.payment.pk}),
            data={"void_reason": "Customer reversal request."},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.payment.refresh_from_db()
        self.fee.refresh_from_db()
        self.assertEqual(self.payment.status, "completed")
        self.assertIsNone(self.payment.voided_at)
        self.assertEqual(self.fee.amount_paid, Decimal("100.00"))


class PaystackPendingFeePaymentReuseTests(TestCase):
    """B4-A: repeated Pay clicks within the dedupe window reuse one pending row."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Dedupe School",
            subdomain="dedupe-sch",
            paystack_subaccount_code="ACCT_testdedupe",
            paystack_subaccount_status="active",
        )
        cls.parent = User.objects.create_user(
            username="dedupe_parent",
            password="pw12345",
            school=cls.school,
            role="parent",
        )
        cls.student_user = User.objects.create_user(
            username="dedupe_student_u",
            password="pw12345",
            school=cls.school,
            role="student",
        )
        cls.student = Student.objects.create(
            school=cls.school,
            user=cls.student_user,
            parent=cls.parent,
            admission_number="DD-001",
            class_name="JHS 1",
        )
        cls.fee = Fee.objects.create(
            school=cls.school,
            student=cls.student,
            amount=Decimal("200.00"),
            amount_paid=Decimal("0.00"),
            paid=False,
        )

    @override_settings(PAYSTACK_SECRET_KEY="sk_test_dummy", PAYSTACK_PUBLIC_KEY="pk_test")
    @patch("finance.views.paystack_service.initialize_payment")
    def test_second_init_reuses_same_pending_fee_payment(self, init_mock):
        init_mock.return_value = {
            "status": True,
            "data": {"authorization_url": "https://checkout.paystack.com/test"},
        }
        self.client.login(username="dedupe_parent", password="pw12345")
        url = reverse("finance:pay", kwargs={"fee_id": self.fee.pk})
        r1 = self.client.get(url)
        self.assertEqual(r1.status_code, 302)
        r2 = self.client.get(url)
        self.assertEqual(r2.status_code, 302)
        pending = list(FeePayment.objects.filter(fee=self.fee, status="pending"))
        self.assertEqual(len(pending), 1)
        self.assertEqual(init_mock.call_count, 2)
        ref1 = init_mock.call_args_list[0][1]["reference"]
        ref2 = init_mock.call_args_list[1][1]["reference"]
        self.assertEqual(ref1, ref2)


class PaymentSuccessAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Pay Success School", subdomain="pay-success-sch")
        cls.owner_parent = User.objects.create_user(
            username="ps_parent_owner", password="pw12345", school=cls.school, role="parent"
        )
        cls.other_parent = User.objects.create_user(
            username="ps_parent_other", password="pw12345", school=cls.school, role="parent"
        )
        cls.student_user = User.objects.create_user(
            username="ps_student_user", password="pw12345", school=cls.school, role="student"
        )
        cls.student = Student.objects.create(
            school=cls.school,
            user=cls.student_user,
            parent=cls.owner_parent,
            admission_number="PS-001",
            class_name="JHS 1",
        )
        cls.fee = Fee.objects.create(
            school=cls.school,
            student=cls.student,
            amount=Decimal("50.00"),
            amount_paid=Decimal("50.00"),
            paid=True,
        )
        cls.reference = "PS_REF_001"
        cls.fee_payment = FeePayment.objects.create(
            fee=cls.fee,
            school=cls.school,
            amount=Decimal("50.00"),
            status="completed",
            paystack_reference=cls.reference,
        )
        PaymentTransaction.objects.create(
            school=cls.school,
            provider="paystack",
            reference=cls.reference,
            amount=Decimal("50.00"),
            currency="GHS",
            status="completed",
            payment_type=PaymentTypes.SCHOOL_FEE,
            object_id=str(cls.fee.pk),
        )

    def test_unrelated_user_cannot_view_payment_success(self):
        self.client.login(username="ps_parent_other", password="pw12345")
        resp = self.client.get(reverse("finance:payment_success"), {"reference": self.reference})
        self.assertEqual(resp.status_code, 302)

    def test_owner_parent_can_view_payment_success(self):
        self.client.login(username="ps_parent_owner", password="pw12345")
        resp = self.client.get(reverse("finance:payment_success"), {"reference": self.reference})
        self.assertEqual(resp.status_code, 200)


class FeeInstallmentMarkPaidTests(TestCase):
    """Regression: marking an installment paid must credit the parent Fee."""

    @classmethod
    def setUpTestData(cls):
        from datetime import date

        cls.school = School.objects.create(name="Inst School", subdomain="inst-sch-01")
        cls.bursar = User.objects.create_user(
            username="inst_bursar",
            password="pw12345",
            school=cls.school,
            role="bursar",
        )
        cls.parent = User.objects.create_user(
            username="inst_parent", password="pw12345", school=cls.school, role="parent"
        )
        cls.student_user = User.objects.create_user(
            username="inst_stu_u", password="pw12345", school=cls.school, role="student"
        )
        cls.student = Student.objects.create(
            school=cls.school,
            user=cls.student_user,
            parent=cls.parent,
            admission_number="INS-001",
            class_name="JHS 1",
        )
        cls.fee = Fee.objects.create(
            school=cls.school,
            student=cls.student,
            amount=Decimal("200.00"),
            amount_paid=Decimal("0.00"),
            paid=False,
        )
        cls.inst = FeeInstallmentPlan.objects.create(
            school=cls.school,
            fee=cls.fee,
            installment_number=1,
            due_date=date.today(),
            amount_due=Decimal("100.00"),
            amount_paid=Decimal("0.00"),
            status="pending",
        )

    def setUp(self):
        self.client = Client()

    def test_mark_paid_credits_parent_fee_balance(self):
        self.client.login(username="inst_bursar", password="pw12345")
        url = reverse("finance:fee_installment_mark_paid", kwargs={"pk": self.inst.pk})
        r = self.client.post(url)
        self.assertEqual(r.status_code, 302)
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.amount_paid, Decimal("100.00"))
        self.inst.refresh_from_db()
        self.assertEqual(self.inst.status, "paid")
        self.assertEqual(self.inst.amount_paid, Decimal("100.00"))

    def test_double_post_does_not_double_credit(self):
        self.client.login(username="inst_bursar", password="pw12345")
        url = reverse("finance:fee_installment_mark_paid", kwargs={"pk": self.inst.pk})
        self.client.post(url)
        self.client.post(url)
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.amount_paid, Decimal("100.00"))

    def test_partial_installment_credits_remaining_only(self):
        self.inst.amount_paid = Decimal("30.00")
        self.inst.status = "partial"
        self.inst.save(update_fields=["amount_paid", "status"])
        self.client.login(username="inst_bursar", password="pw12345")
        url = reverse("finance:fee_installment_mark_paid", kwargs={"pk": self.inst.pk})
        self.client.post(url)
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.amount_paid, Decimal("70.00"))


class FinanceAdminErpFeatureGateTests(TestCase):
    """Purchase orders, bank accounts, and fixed assets require SchoolFeature('finance_admin')."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Fin ERP Gate School", subdomain=f"fin-erp-{uuid.uuid4().hex[:10]}")
        SchoolFeature.objects.update_or_create(
            school=cls.school, key="finance_admin", defaults={"enabled": False}
        )
        cls.admin = User.objects.create_user(
            username="fin_erp_admin", password="pw12345", school=cls.school, role="school_admin"
        )

    def setUp(self):
        self.client = Client()

    def test_purchase_order_list_redirects_when_finance_admin_disabled(self):
        self.client.login(username="fin_erp_admin", password="pw12345")
        r = self.client.get(reverse("finance:purchase_order_list"))
        self.assertRedirects(r, reverse("accounts:dashboard"), fetch_redirect_response=False)

    def test_fixed_asset_list_redirects_when_finance_admin_disabled(self):
        self.client.login(username="fin_erp_admin", password="pw12345")
        r = self.client.get(reverse("finance:fixed_asset_list"))
        self.assertRedirects(r, reverse("accounts:dashboard"), fetch_redirect_response=False)

    def test_bank_account_list_redirects_when_finance_admin_disabled(self):
        self.client.login(username="fin_erp_admin", password="pw12345")
        r = self.client.get(reverse("finance:bank_account_list"))
        self.assertRedirects(r, reverse("accounts:dashboard"), fetch_redirect_response=False)


class FeeManagementErpFeatureGateTests(TestCase):
    """Fee discounts, installments, and bulk fee generation require SchoolFeature('fee_management')."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Fee Mgmt Gate School", subdomain=f"fee-mgt-{uuid.uuid4().hex[:10]}")
        SchoolFeature.objects.update_or_create(
            school=cls.school, key="fee_management", defaults={"enabled": False}
        )
        cls.admin = User.objects.create_user(
            username="fee_mgt_admin", password="pw12345", school=cls.school, role="school_admin"
        )

    def setUp(self):
        self.client = Client()

    def test_fee_discount_list_redirects_when_fee_management_disabled(self):
        self.client.login(username="fee_mgt_admin", password="pw12345")
        r = self.client.get(reverse("finance:fee_discount_list"))
        self.assertRedirects(r, reverse("accounts:dashboard"), fetch_redirect_response=False)

    def test_fee_installment_list_redirects_when_fee_management_disabled(self):
        self.client.login(username="fee_mgt_admin", password="pw12345")
        r = self.client.get(reverse("finance:fee_installment_list"))
        self.assertRedirects(r, reverse("accounts:dashboard"), fetch_redirect_response=False)

    def test_bulk_fee_generate_redirects_when_fee_management_disabled(self):
        self.client.login(username="fee_mgt_admin", password="pw12345")
        r = self.client.get(reverse("finance:bulk_fee_generate"))
        self.assertRedirects(r, reverse("accounts:dashboard"), fetch_redirect_response=False)


class FeeStructureCoverageTests(TestCase):
    """Coverage page counts in-scope students and POST backfills missing Fee rows."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Cov Fee School", subdomain=f"cov-fee-{uuid.uuid4().hex[:10]}")
        SchoolFeature.objects.update_or_create(
            school=cls.school, key="fee_management", defaults={"enabled": True}
        )
        cls.admin = User.objects.create_user(
            username="cov_fee_admin", password="pw12345", school=cls.school, role="school_admin"
        )
        from academics.models import Term

        cls.term = Term.objects.create(school=cls.school, name="Term 1", is_current=True)
        cls.structure = FeeStructure.objects.create(
            school=cls.school,
            name="Tuition",
            amount=Decimal("100.00"),
            class_name="JHS1",
            term_fk=cls.term,
        )
        u1 = User.objects.create_user(
            username="cov_stu1", password="pw12345", school=cls.school, role="student", first_name="A", last_name="One"
        )
        u2 = User.objects.create_user(
            username="cov_stu2", password="pw12345", school=cls.school, role="student", first_name="B", last_name="Two"
        )
        cls.st1 = Student.objects.create(
            school=cls.school, user=u1, admission_number="C1", class_name="JHS1"
        )
        cls.st2 = Student.objects.create(
            school=cls.school, user=u2, admission_number="C2", class_name="JHS1"
        )
        Fee.objects.create(
            school=cls.school,
            student=cls.st1,
            fee_structure=cls.structure,
            term=cls.term,
            amount=Decimal("100.00"),
        )

    def setUp(self):
        self.client = Client()
        from django.core.cache import cache

        SchoolFeature.objects.update_or_create(
            school=self.school, key="fee_management", defaults={"enabled": True}
        )
        cache.delete(School._feature_cache_key(self.school.pk))

    def test_coverage_get_shows_one_missing(self):
        self.client.login(username="cov_fee_admin", password="pw12345")
        url = reverse("finance:fee_structure_coverage", args=[self.structure.pk])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Missing fee rows")
        self.assertContains(r, "Create 1 missing fee record")
        self.assertContains(r, "C2")

    def test_coverage_post_creates_missing_fee(self):
        self.assertEqual(Fee.objects.filter(fee_structure=self.structure).count(), 1)
        self.client.login(username="cov_fee_admin", password="pw12345")
        url = reverse("finance:fee_structure_coverage", args=[self.structure.pk])
        r = self.client.post(url, {})
        self.assertRedirects(r, url, fetch_redirect_response=False)
        self.assertEqual(Fee.objects.filter(fee_structure=self.structure).count(), 2)

    def test_coverage_redirects_when_fee_management_disabled(self):
        SchoolFeature.objects.update_or_create(
            school=self.school, key="fee_management", defaults={"enabled": False}
        )
        self.client.login(username="cov_fee_admin", password="pw12345")
        r = self.client.get(reverse("finance:fee_structure_coverage", args=[self.structure.pk]))
        self.assertRedirects(r, reverse("accounts:dashboard"), fetch_redirect_response=False)
