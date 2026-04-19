"""Paystack gross-up (pass processing estimate to payer)."""

from decimal import Decimal

from django.test import SimpleTestCase, override_settings

from finance.paystack_service import compute_paystack_gross_from_net

from django.test import Client, TestCase
from django.urls import reverse

from finance.models import PaymentTransaction
from schools.models import School
from accounts.models import User
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
