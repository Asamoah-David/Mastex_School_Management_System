"""
Unit tests for the Ghana payroll gross-to-net engine.
No database access required — pure arithmetic tests.
Run with: pytest accounts/tests_payroll_engine.py -v
"""
from decimal import Decimal

import pytest

from accounts.payroll_engine import compute_payroll, _compute_paye, PayrollResult


class TestPAYEBands:
    """Ghana GRA 2024 monthly PAYE band calculations."""

    def test_zero_taxable_income(self):
        assert _compute_paye(Decimal("0")) == Decimal("0")

    def test_within_first_exempt_band(self):
        # First 319 GHS is 0%
        assert _compute_paye(Decimal("319")) == Decimal("0")

    def test_second_band_five_percent(self):
        # 319 exempt + 319 at 5% = 15.95
        result = _compute_paye(Decimal("638"))
        assert result == Decimal("15.95")

    def test_three_bands(self):
        # 319@0% + 319@5% + 880@10% = 0 + 15.95 + 88.00 = 103.95
        result = _compute_paye(Decimal("1518"))
        assert result == Decimal("103.95")

    def test_negative_taxable_clamped_to_zero(self):
        assert _compute_paye(Decimal("-100")) == Decimal("0")


class TestComputePayroll:
    def test_gross_zero(self):
        r = compute_payroll(Decimal("0"))
        assert r.net_pay == Decimal("0")
        assert r.ssnit_employee == Decimal("0")
        assert r.paye == Decimal("0")

    def test_ssnit_rate(self):
        r = compute_payroll(Decimal("2000"))
        expected_ssnit = (Decimal("2000") * Decimal("0.055")).quantize(Decimal("0.01"))
        assert r.ssnit_employee == expected_ssnit

    def test_employer_ssnit_not_deducted_from_net(self):
        r = compute_payroll(Decimal("2000"))
        # employer SSNIT is informational only — net_pay must NOT subtract it
        assert r.net_pay == r.gross_pay - r.ssnit_employee - r.paye

    def test_net_plus_deductions_equals_gross(self):
        for gross in ("1000", "3000", "5000", "15000", "50000"):
            r = compute_payroll(Decimal(gross))
            assert r.net_pay + r.total_deductions == r.gross_pay, f"Failed for gross={gross}"

    def test_extra_deductions_reduce_net(self):
        r_no_extra = compute_payroll(Decimal("5000"))
        r_with_extra = compute_payroll(Decimal("5000"), extra_deductions=Decimal("200"))
        assert r_with_extra.net_pay == r_no_extra.net_pay - Decimal("200")

    def test_to_dict_contains_all_keys(self):
        r = compute_payroll(Decimal("3000"))
        d = r.to_dict()
        for key in ("gross_pay", "ssnit_employee", "ssnit_employer", "taxable_income", "paye", "total_deductions", "net_pay"):
            assert key in d, f"Missing key: {key}"

    def test_result_is_payroll_result_instance(self):
        assert isinstance(compute_payroll(Decimal("5000")), PayrollResult)

    def test_high_earner_top_band(self):
        # GHS 100,000 should reach the 30% band
        r = compute_payroll(Decimal("100000"))
        assert r.paye > Decimal("20000")
        assert r.net_pay < r.gross_pay

    def test_rounding_two_decimal_places(self):
        r = compute_payroll(Decimal("1234.56"))
        for val in (r.gross_pay, r.ssnit_employee, r.net_pay, r.paye):
            assert val == val.quantize(Decimal("0.01")), f"{val} not 2dp"
