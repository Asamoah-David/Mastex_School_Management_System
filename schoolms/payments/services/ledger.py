from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from django.conf import settings


class PaymentTypes:
    SCHOOL_FEE = "school_fee"
    SCHOOL_FEE_MANUAL = "school_fee_manual"
    SCHOOL_FEE_OFFLINE = "school_fee_offline"
    CANTEEN = "canteen"
    BUS = "bus"
    TEXTBOOK = "textbook"
    HOSTEL = "hostel"


_PAYMENT_TYPE_CT_MAP = {
    PaymentTypes.SCHOOL_FEE:         ("finance",     "fee"),
    PaymentTypes.SCHOOL_FEE_MANUAL:  ("finance",     "fee"),
    PaymentTypes.SCHOOL_FEE_OFFLINE: ("finance",     "fee"),
    PaymentTypes.CANTEEN:            ("operations",  "canteenpayment"),
    PaymentTypes.BUS:                ("operations",  "buspayment"),
    PaymentTypes.TEXTBOOK:           ("operations",  "textbooksale"),
    PaymentTypes.HOSTEL:             ("operations",  "hostelfee"),
}


def _resolve_content_type(payment_type: str):
    """Return ContentType instance for a payment_type string, or None."""
    entry = _PAYMENT_TYPE_CT_MAP.get(payment_type)
    if not entry:
        return None
    try:
        from django.contrib.contenttypes.models import ContentType
        return ContentType.objects.get(app_label=entry[0], model=entry[1])
    except Exception:
        return None


def record_payment_transaction(
    *,
    provider: str = "paystack",
    reference: str,
    school_id: Optional[int],
    amount: Any,
    status: str,
    payment_type: str,
    object_id: str = "",
    metadata: Optional[dict] = None,
) -> None:
    if not reference:
        return

    provider = (provider or "").strip().lower() or provider
    status = (status or "").strip().lower() or status
    if status not in ("pending", "completed", "failed"):
        return

    if payment_type == "fee":
        payment_type = PaymentTypes.SCHOOL_FEE

    from finance.models import PaymentTransaction

    amt = amount
    if not isinstance(amt, Decimal):
        try:
            amt = Decimal(str(amt or 0))
        except Exception:
            amt = Decimal("0")

    if status == "failed":
        try:
            if PaymentTransaction.objects.filter(reference=reference, status="completed").exists():
                return
        except Exception:
            return

    ct = _resolve_content_type(payment_type)

    try:
        PaymentTransaction.objects.update_or_create(
            reference=reference,
            defaults={
                "provider": provider,
                "school_id": school_id,
                "amount": amt,
                "currency": getattr(settings, "PAYSTACK_CURRENCY", "GHS"),
                "status": status,
                "payment_type": payment_type,
                "object_id": object_id or "",
                "content_type": ct,
                "metadata": metadata or {},
            },
        )
    except Exception:
        return
