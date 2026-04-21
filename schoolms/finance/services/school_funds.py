"""
School Funds Ledger — service layer (Phase 2).

All fund state transitions go through this module.
Every public function runs inside ``transaction.atomic()`` and creates
a ``SchoolFundsLedgerEntry`` + updates ``SchoolFundsBalance`` atomically.

Rules:
- Ledger entries are append-only (never updated or deleted).
- Balance row is locked with ``select_for_update()`` before mutation.
- All amounts must be positive ``Decimal`` values.
- Cross-school writes are prevented by requiring explicit ``school_id``.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

from django.db import models, transaction

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")


def _to_decimal(value) -> Decimal:
    """Coerce to Decimal, raise on invalid."""
    if isinstance(value, Decimal):
        return value
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid amount: {value!r}") from exc
    return d


def _get_or_create_balance(school_id: int):
    """
    Return the ``SchoolFundsBalance`` row for ``school_id``, locked for update.
    Creates the row (all zeros) if it doesn't exist yet.
    """
    from finance.models import SchoolFundsBalance

    bal, _created = SchoolFundsBalance.objects.select_for_update().get_or_create(
        school_id=school_id,
    )
    return bal


def _create_entry(
    *,
    school_id: int,
    amount: Decimal,
    direction: str,
    state: str,
    source_type: str,
    reference: str,
    description: str = "",
    currency: str = "GHS",
    metadata: Optional[dict] = None,
):
    """Create a ledger entry (must be called inside transaction.atomic)."""
    from finance.models import SchoolFundsLedgerEntry

    if amount <= _ZERO:
        raise ValueError(f"Ledger amount must be positive, got {amount}")
    if direction not in ("credit", "debit"):
        raise ValueError(f"Invalid direction: {direction}")

    return SchoolFundsLedgerEntry.objects.create(
        school_id=school_id,
        amount=amount,
        direction=direction,
        state=state,
        source_type=source_type,
        reference=reference,
        description=description[:500],
        currency=currency,
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
#  Public API — each function is one atomic fund state transition
# ---------------------------------------------------------------------------


def record_fee_collected(
    *,
    school_id: int,
    amount,
    reference: str,
    description: str = "",
    currency: str = "GHS",
    metadata: Optional[dict] = None,
) -> None:
    """
    Called when a fee payment is confirmed (charge.success).

    Transition: → collected (credit).
    For simplicity in Phase 2, we also immediately credit ``available``
    since Paystack subaccount settlement is handled externally.
    When settlement reconciliation is implemented (Phase 3+), this will
    instead only credit ``collected``, and a separate reconciliation
    step will move funds to ``cleared`` → ``available``.
    """
    amt = _to_decimal(amount).quantize(Decimal("0.01"))
    if amt <= _ZERO:
        return

    with transaction.atomic():
        bal = _get_or_create_balance(school_id)

        # 1. Record collected
        _create_entry(
            school_id=school_id,
            amount=amt,
            direction="credit",
            state="collected",
            source_type="fee_payment",
            reference=reference,
            description=description or "Fee payment collected",
            currency=currency,
            metadata=metadata,
        )
        bal.collected_total = models.F("collected_total") + amt

        # 2. Immediately mark as available (Phase 2 simplification).
        #    Phase 3 will split this into cleared → available via reconciliation.
        _create_entry(
            school_id=school_id,
            amount=amt,
            direction="credit",
            state="available",
            source_type="settlement",
            reference=reference,
            description="Auto-available (settlement reconciliation pending)",
            currency=currency,
            metadata=metadata,
        )
        bal.available_total = models.F("available_total") + amt

        bal.save(update_fields=["collected_total", "available_total", "updated_at"])

    logger.info(
        "school_funds: collected school=%s amount=%s ref=%s",
        school_id, amt, reference,
    )


def reserve_funds(
    *,
    school_id: int,
    amount,
    reference: str,
    description: str = "",
    currency: str = "GHS",
    metadata: Optional[dict] = None,
) -> bool:
    """
    Lock funds for a pending payout.

    Transition: available (debit) → reserved (credit).
    Returns True if reservation succeeded, False if insufficient funds.
    """
    amt = _to_decimal(amount).quantize(Decimal("0.01"))
    if amt <= _ZERO:
        return False

    with transaction.atomic():
        bal = _get_or_create_balance(school_id)
        # Refresh to get actual values (not F-expression residuals)
        bal.refresh_from_db()

        if bal.available_total < amt:
            logger.warning(
                "school_funds: reserve FAILED school=%s requested=%s available=%s ref=%s",
                school_id, amt, bal.available_total, reference,
            )
            return False

        _create_entry(
            school_id=school_id,
            amount=amt,
            direction="debit",
            state="available",
            source_type="payout_reserve",
            reference=reference,
            description=description or "Funds reserved for payout",
            currency=currency,
            metadata=metadata,
        )
        _create_entry(
            school_id=school_id,
            amount=amt,
            direction="credit",
            state="reserved",
            source_type="payout_reserve",
            reference=reference,
            description=description or "Funds reserved for payout",
            currency=currency,
            metadata=metadata,
        )

        bal.available_total = models.F("available_total") - amt
        bal.reserved_total = models.F("reserved_total") + amt
        bal.save(update_fields=["available_total", "reserved_total", "updated_at"])

    logger.info(
        "school_funds: reserved school=%s amount=%s ref=%s",
        school_id, amt, reference,
    )
    return True


def release_reserved_funds(
    *,
    school_id: int,
    amount,
    reference: str,
    description: str = "",
    currency: str = "GHS",
    metadata: Optional[dict] = None,
) -> None:
    """
    Release reserved funds back to available (payout failed or cancelled).

    Transition: reserved (debit) → available (credit).
    """
    amt = _to_decimal(amount).quantize(Decimal("0.01"))
    if amt <= _ZERO:
        return

    with transaction.atomic():
        bal = _get_or_create_balance(school_id)

        _create_entry(
            school_id=school_id,
            amount=amt,
            direction="debit",
            state="reserved",
            source_type="payout_release",
            reference=reference,
            description=description or "Reserved funds released (payout failed/cancelled)",
            currency=currency,
            metadata=metadata,
        )
        _create_entry(
            school_id=school_id,
            amount=amt,
            direction="credit",
            state="available",
            source_type="payout_release",
            reference=reference,
            description=description or "Reserved funds released (payout failed/cancelled)",
            currency=currency,
            metadata=metadata,
        )

        bal.reserved_total = models.F("reserved_total") - amt
        bal.available_total = models.F("available_total") + amt
        bal.save(update_fields=["reserved_total", "available_total", "updated_at"])

    logger.info(
        "school_funds: released school=%s amount=%s ref=%s",
        school_id, amt, reference,
    )


def mark_funds_paid_out(
    *,
    school_id: int,
    amount,
    reference: str,
    description: str = "",
    currency: str = "GHS",
    metadata: Optional[dict] = None,
) -> None:
    """
    Confirm payout execution (transfer.success).

    Transition: reserved (debit) → paid_out (credit).
    """
    amt = _to_decimal(amount).quantize(Decimal("0.01"))
    if amt <= _ZERO:
        return

    with transaction.atomic():
        bal = _get_or_create_balance(school_id)

        _create_entry(
            school_id=school_id,
            amount=amt,
            direction="debit",
            state="reserved",
            source_type="payout_execute",
            reference=reference,
            description=description or "Payout executed",
            currency=currency,
            metadata=metadata,
        )
        _create_entry(
            school_id=school_id,
            amount=amt,
            direction="credit",
            state="paid_out",
            source_type="payout_execute",
            reference=reference,
            description=description or "Payout executed",
            currency=currency,
            metadata=metadata,
        )

        bal.reserved_total = models.F("reserved_total") - amt
        bal.paid_out_total = models.F("paid_out_total") + amt
        bal.save(update_fields=["reserved_total", "paid_out_total", "updated_at"])

    logger.info(
        "school_funds: paid_out school=%s amount=%s ref=%s",
        school_id, amt, reference,
    )


def get_balance(school_id: int) -> dict:
    """
    Return current balance snapshot for a school (read-only, no lock).
    Returns a dict with all totals; creates the row if missing.
    """
    from finance.models import SchoolFundsBalance

    bal, _ = SchoolFundsBalance.objects.get_or_create(school_id=school_id)
    return {
        "collected_total": bal.collected_total,
        "cleared_total": bal.cleared_total,
        "available_total": bal.available_total,
        "reserved_total": bal.reserved_total,
        "paid_out_total": bal.paid_out_total,
        "last_reconciled_at": bal.last_reconciled_at,
        "updated_at": bal.updated_at,
    }


def rebuild_balance_from_ledger(school_id: int) -> dict:
    """
    Recompute ``SchoolFundsBalance`` from the ledger entries.

    Use for reconciliation audits — not in hot paths.
    """
    from finance.models import SchoolFundsBalance, SchoolFundsLedgerEntry

    entries = SchoolFundsLedgerEntry.objects.filter(school_id=school_id)
    totals = {
        "collected_total": _ZERO,
        "cleared_total": _ZERO,
        "available_total": _ZERO,
        "reserved_total": _ZERO,
        "paid_out_total": _ZERO,
    }
    state_field_map = {
        "collected": "collected_total",
        "cleared": "cleared_total",
        "available": "available_total",
        "reserved": "reserved_total",
        "paid_out": "paid_out_total",
    }
    for entry in entries.iterator():
        field = state_field_map.get(entry.state)
        if not field:
            continue
        if entry.direction == "credit":
            totals[field] += entry.amount
        elif entry.direction == "debit":
            totals[field] -= entry.amount

    with transaction.atomic():
        bal, _ = SchoolFundsBalance.objects.select_for_update().get_or_create(
            school_id=school_id,
        )
        for k, v in totals.items():
            setattr(bal, k, max(v, _ZERO))
        from django.utils import timezone
        bal.last_reconciled_at = timezone.now()
        bal.save()

    logger.info("school_funds: rebuilt balance school=%s totals=%s", school_id, totals)
    return totals
