"""
Payroll gross-to-net calculation engine.

Implements Ghana statutory deductions:
  - SSNIT (Employee contribution):  5.5 % of basic salary
  - SSNIT (Employer contribution):  13.0% of basic salary (employer cost, not deducted from employee)
  - PAYE income tax:                Graduated bands per GRA 2024 schedule

Usage::

    from accounts.payroll_engine import compute_payroll

    result = compute_payroll(gross=Decimal("5000"))
    # result.net_pay, result.paye, result.ssnit_employee, ...

Or use the helper to persist deductions on a StaffPayrollPayment::

    from accounts.payroll_engine import apply_payroll_to_payment
    apply_payroll_to_payment(payment_instance, gross=Decimal("5000"))
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict


# ---------------------------------------------------------------------------
# Ghana PAYE tax bands (monthly, GHS) — GRA 2024 schedule
# Each tuple: (band_limit, rate)  — Decimal('Infinity') for the last band
# ---------------------------------------------------------------------------
_PAYE_BANDS: List[tuple] = [
    (Decimal("319"),     Decimal("0")),          # 0 % on first 319
    (Decimal("319"),     Decimal("0.05")),        # 5 % on next 319
    (Decimal("880"),     Decimal("0.10")),        # 10 % on next 880
    (Decimal("1_467"),   Decimal("0.175")),       # 17.5 % on next 1 467
    (Decimal("29_008"),  Decimal("0.25")),        # 25 % on next 29 008
    (Decimal("Infinity"), Decimal("0.30")),       # 30 % on remainder
]

_SSNIT_EMPLOYEE_RATE = Decimal("0.055")   # 5.5 %
_SSNIT_EMPLOYER_RATE = Decimal("0.130")   # 13.0 %
_TWO_DP              = Decimal("0.01")


def _round(amount: Decimal) -> Decimal:
    return amount.quantize(_TWO_DP, rounding=ROUND_HALF_UP)


def _compute_paye(taxable: Decimal) -> Decimal:
    """Compute monthly PAYE on taxable income using Ghana GRA 2024 bands."""
    paye = Decimal("0")
    remaining = max(taxable, Decimal("0"))
    for band_limit, rate in _PAYE_BANDS:
        if remaining <= 0:
            break
        taxable_in_band = min(remaining, band_limit)
        paye += taxable_in_band * rate
        remaining -= taxable_in_band
    return _round(paye)


@dataclass
class PayrollResult:
    gross_pay:           Decimal
    ssnit_employee:      Decimal
    ssnit_employer:      Decimal
    taxable_income:      Decimal
    paye:                Decimal
    total_deductions:    Decimal
    net_pay:             Decimal
    breakdown:           Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "gross_pay":        str(self.gross_pay),
            "ssnit_employee":   str(self.ssnit_employee),
            "ssnit_employer":   str(self.ssnit_employer),
            "taxable_income":   str(self.taxable_income),
            "paye":             str(self.paye),
            "total_deductions": str(self.total_deductions),
            "net_pay":          str(self.net_pay),
        }


def compute_payroll(gross: Decimal, extra_deductions: Decimal = Decimal("0")) -> PayrollResult:
    """Compute Ghana statutory gross-to-net for a given monthly gross salary.

    Args:
        gross:             Total gross pay (basic + allowances) in GHS.
        extra_deductions:  Any school-specific additional deductions (loans, etc.).

    Returns:
        A :class:`PayrollResult` with all deduction components and net pay.
    """
    gross = _round(Decimal(str(gross)))
    extra_deductions = _round(Decimal(str(extra_deductions or 0)))

    ssnit_employee = _round(gross * _SSNIT_EMPLOYEE_RATE)
    ssnit_employer = _round(gross * _SSNIT_EMPLOYER_RATE)

    # Taxable income = gross - employee SSNIT
    taxable_income = max(gross - ssnit_employee, Decimal("0"))
    paye = _compute_paye(taxable_income)

    total_deductions = ssnit_employee + paye + extra_deductions
    net_pay = _round(gross - total_deductions)

    return PayrollResult(
        gross_pay=gross,
        ssnit_employee=ssnit_employee,
        ssnit_employer=ssnit_employer,
        taxable_income=taxable_income,
        paye=paye,
        total_deductions=total_deductions,
        net_pay=net_pay,
    )


def apply_payroll_to_payment(payment, gross: Decimal, extra_deductions: Decimal = Decimal("0")) -> PayrollResult:
    """Compute gross-to-net and persist the deductions breakdown on a ``StaffPayrollPayment`` instance.

    Saves ``gross_amount``, ``net_amount`` and ``deductions_breakdown`` fields.
    The caller is responsible for calling ``payment.save()`` afterwards.
    """
    result = compute_payroll(gross=gross, extra_deductions=extra_deductions)
    if hasattr(payment, "gross_amount"):
        payment.gross_amount = result.gross_pay
    if hasattr(payment, "net_amount"):
        payment.net_amount = result.net_pay
    if hasattr(payment, "deductions_breakdown"):
        payment.deductions_breakdown = result.to_dict()
    return result
