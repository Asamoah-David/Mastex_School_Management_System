"""
Outgoing Paystack transfers for staff payroll (merchant balance → staff MoMo/bank).
"""
from __future__ import annotations

import re
import uuid
from decimal import Decimal

from django.conf import settings

from finance.paystack_service import paystack_service


def staff_paystack_transfers_enabled() -> bool:
    return bool(getattr(settings, "PAYSTACK_SECRET_KEY", "")) and getattr(
        settings, "PAYSTACK_STAFF_TRANSFERS_ENABLED", False
    )


def normalize_gh_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 10 and digits.startswith("0"):
        return digits
    if len(digits) == 12 and digits.startswith("233"):
        return "0" + digits[3:]
    return digits


def _recipient_name(user) -> str:
    name = user.get_full_name() or user.username
    return name[:100]


def recipient_snapshot_for_route(user, route: str) -> str:
    if route == "momo":
        d = normalize_gh_phone(getattr(user, "payroll_momo_number", "") or "")
        net = (getattr(user, "payroll_momo_network", "") or "").strip()
        if len(d) >= 4:
            return f"MoMo {net} ***{d[-4:]}"
        return f"MoMo {net}".strip()
    if route == "bank":
        ac = (getattr(user, "payroll_bank_account_number", "") or "").strip()
        if len(ac) >= 4:
            return f"Bank ***{ac[-4:]}"
        return "Bank transfer"
    return ""


def ensure_paystack_recipient_for_staff(user, *, route: str) -> tuple[str | None, str | None]:
    """
    route: 'momo' or 'bank'
    Returns (recipient_code, error_message).
    """
    if route not in ("momo", "bank"):
        return None, "Invalid payout route."

    if not staff_paystack_transfers_enabled():
        return None, "Paystack staff transfers are not enabled (set PAYSTACK_STAFF_TRANSFERS_ENABLED=1 and PAYSTACK_SECRET_KEY)."

    if route == "momo":
        momo = normalize_gh_phone(getattr(user, "payroll_momo_number", "") or "")
        net = (getattr(user, "payroll_momo_network", "") or "").strip().upper()
        if not momo or not net:
            return None, "Save mobile money number and network on the staff profile first."
        if net not in ("MTN", "VOD", "ATL"):
            return None, "Select a valid mobile money network (MTN, Telecel, AirtelTigo)."
        cached = (getattr(user, "paystack_recipient_momo", "") or "").strip()
        if cached.startswith("RCP_"):
            return cached, None
        bank_map = {"MTN": "MTN", "VOD": "VOD", "ATL": "ATL"}
        pcode = bank_map.get(net, net)
        resp = paystack_service.create_transfer_recipient(
            recipient_type="mobile_money",
            name=_recipient_name(user),
            account_number=momo,
            bank_code=pcode,
            currency=getattr(settings, "PAYSTACK_CURRENCY", "GHS"),
        )
        if not resp.get("status"):
            return None, resp.get("message") or "Could not create mobile-money recipient."
        code = (resp.get("data") or {}).get("recipient_code") or (resp.get("data") or {}).get("code")
        if not code:
            return None, "Paystack did not return a recipient code."
        code = str(code)
        user.paystack_recipient_momo = code
        user.save(update_fields=["paystack_recipient_momo"])
        return code, None

    bank_acct = (getattr(user, "payroll_bank_account_number", "") or "").strip()
    bank_code = (getattr(user, "payroll_bank_code", "") or "").strip()
    if not bank_acct or not bank_code:
        return None, "Save bank account number and Paystack bank code on the staff profile first."
    cached = (getattr(user, "paystack_recipient_bank", "") or "").strip()
    if cached.startswith("RCP_"):
        return cached, None
    name = (getattr(user, "payroll_bank_account_name", "") or "").strip() or _recipient_name(user)
    resp = paystack_service.create_transfer_recipient(
        recipient_type="nuban",
        name=name[:100],
        account_number=bank_acct,
        bank_code=bank_code,
        currency=getattr(settings, "PAYSTACK_CURRENCY", "GHS"),
    )
    if not resp.get("status"):
        return None, resp.get("message") or "Could not create bank recipient."
    code = (resp.get("data") or {}).get("recipient_code") or (resp.get("data") or {}).get("code")
    if not code:
        return None, "Paystack did not return a recipient code."
    code = str(code)
    user.paystack_recipient_bank = code
    user.save(update_fields=["paystack_recipient_bank"])
    return code, None


def generate_payroll_reference() -> str:
    return f"STF{uuid.uuid4().hex[:24].upper()}"


def initiate_staff_payroll_paystack_transfer(
    *,
    payment,
    staff_user,
    reason: str,
    route: str,
) -> tuple[bool, str]:
    """payment must be saved (pk set). Sets reference and Paystack fields."""
    if not payment.pk:
        return False, "Payment row must be saved before initiating transfer."

    rcpt, err = ensure_paystack_recipient_for_staff(staff_user, route=route)
    if not rcpt:
        return False, err or "No recipient."

    ref = (payment.reference or "").strip() or generate_payroll_reference()
    payment.reference = ref
    payment.save(update_fields=["reference"])
    meta = {
        "payment_type": "staff_payroll",
        "staff_payroll_payment_id": payment.pk,
    }
    resp = paystack_service.initiate_transfer(
        amount_major=payment.amount,
        recipient_code=rcpt,
        reason=reason,
        reference=ref,
        currency=payment.currency or getattr(settings, "PAYSTACK_CURRENCY", "GHS"),
        metadata=meta,
    )
    if not resp.get("status"):
        msg = resp.get("message") or "Transfer request failed."
        payment.paystack_status = "failed"
        payment.paystack_failure_reason = msg[:2000]
        payment.save(update_fields=["paystack_status", "paystack_failure_reason", "reference"])
        return False, msg

    data = resp.get("data") or {}
    payment.paystack_transfer_code = str(data.get("transfer_code") or data.get("code") or "")[:64]
    payment.paystack_status = "pending"
    payment.paystack_failure_reason = ""
    payment.save(
        update_fields=["paystack_transfer_code", "paystack_status", "paystack_failure_reason", "reference"]
    )
    return True, data.get("message") or "Transfer queued. Status will update via Paystack webhook."
