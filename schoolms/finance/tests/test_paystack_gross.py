"""Paystack gross-up (pass processing estimate to payer)."""

from decimal import Decimal

from django.test import SimpleTestCase, override_settings

from finance.paystack_service import compute_paystack_gross_from_net


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
