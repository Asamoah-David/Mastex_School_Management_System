"""
Staff Payout Request service layer — Phase 2.

Handles the request → approve → reserve → (cancel/reject) lifecycle.
Does NOT handle execution (Phase C/D).
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class PayoutError(Exception):
    """Raised for business-rule violations in payout workflow."""
    pass


def create_payout_request(
    *,
    school_id: int,
    staff_user_id: int,
    amount: Decimal,
    period_label: str,
    route: str,
    requested_by_id: int,
    reason: str = "",
    currency: str = "GHS",
    recipient_snapshot: str = "",
):
    """
    Create a new payout request in ``pending_approval`` status.

    Validates:
    - staff belongs to school
    - no duplicate active request for same staff+period
    - amount > 0
    """
    from finance.models import StaffPayoutRequest
    from accounts.models import User
    from audit.services import write_audit

    if amount <= 0:
        raise PayoutError("Amount must be greater than zero.")
    if route not in ("momo", "bank"):
        raise PayoutError("Route must be 'momo' or 'bank'.")
    if not period_label.strip():
        raise PayoutError("Period label is required.")

    staff = User.objects.filter(pk=staff_user_id).first()
    if not staff or getattr(staff, "school_id", None) != school_id:
        raise PayoutError("Staff member does not belong to this school.")

    # Duplicate prevention: no active request for same staff + period in this school
    active_statuses = ("pending_approval", "approved", "funds_reserved", "executing")
    duplicate = StaffPayoutRequest.objects.filter(
        school_id=school_id,
        staff_user_id=staff_user_id,
        period_label=period_label,
        status__in=active_statuses,
    ).exists()
    if duplicate:
        raise PayoutError(
            f"An active payout request already exists for this staff member "
            f"for period '{period_label}'."
        )

    req = StaffPayoutRequest.objects.create(
        school_id=school_id,
        staff_user_id=staff_user_id,
        amount=amount,
        currency=currency,
        period_label=period_label,
        route=route,
        reason=reason[:200],
        requested_by_id=requested_by_id,
        recipient_snapshot=recipient_snapshot[:200],
        status="pending_approval",
    )
    logger.info(
        "payout_request: created ref=%s school=%s staff=%s amount=%s by=%s",
        req.reference, school_id, staff_user_id, amount, requested_by_id,
    )
    try:
        requester = staff if staff.pk == requested_by_id else User.objects.filter(pk=requested_by_id).first()
        write_audit(
            user=requester,
            action="payout_request_created",
            model_name="finance.StaffPayoutRequest",
            object_id=req.pk,
            school_id=school_id,
            changes={
                "staff_user_id": staff_user_id,
                "amount": str(amount),
                "period": period_label,
                "route": route,
            },
        )
    except Exception:
        logger.exception("payout_request: audit log failed for ref=%s", req.reference)
    return req


def approve_payout_request(*, request_id: int, approved_by_id: int):
    """
    Approve a pending payout request.

    Validates:
    - request is in ``pending_approval``
    - approver differs from requester (maker-checker)
    - approver belongs to same school
    """
    from finance.models import StaffPayoutRequest

    with transaction.atomic():
        req = (
            StaffPayoutRequest.objects.select_for_update()
            .filter(pk=request_id)
            .first()
        )
        if not req:
            raise PayoutError("Payout request not found.")
        if req.status != "pending_approval":
            raise PayoutError(f"Cannot approve request in status '{req.status}'.")
        if req.requested_by_id == approved_by_id:
            raise PayoutError(
                "Maker-checker violation: the approver cannot be the same person "
                "who created the request."
            )

        from accounts.models import User
        approver = User.objects.filter(pk=approved_by_id).first()
        if not approver or getattr(approver, "school_id", None) != req.school_id:
            raise PayoutError("Approver does not belong to this school.")

        req.status = "approved"
        req.approved_by_id = approved_by_id
        req.approved_at = timezone.now()
        req.save(update_fields=["status", "approved_by_id", "approved_at"])

    logger.info(
        "payout_request: approved ref=%s by=%s", req.reference, approved_by_id,
    )
    return req


def reserve_funds_for_payout(*, request_id: int):
    """
    Reserve funds from the school's available balance for an approved payout.

    Transitions: approved → funds_reserved
    """
    from finance.models import StaffPayoutRequest
    from finance.services.school_funds import reserve_funds

    with transaction.atomic():
        req = (
            StaffPayoutRequest.objects.select_for_update()
            .filter(pk=request_id)
            .first()
        )
        if not req:
            raise PayoutError("Payout request not found.")
        if req.status != "approved":
            raise PayoutError(f"Cannot reserve funds for request in status '{req.status}'.")

        ledger_ref = f"RESERVE-{req.reference}"
        ok = reserve_funds(
            school_id=req.school_id,
            amount=req.amount,
            reference=ledger_ref,
            description=f"Reserve for payout {req.reference} to staff #{req.staff_user_id}",
            currency=req.currency,
            metadata={
                "payout_request_id": req.pk,
                "payout_reference": req.reference,
                "staff_user_id": req.staff_user_id,
            },
        )
        if not ok:
            raise PayoutError(
                "Insufficient available funds. Cannot reserve for this payout."
            )

        req.status = "funds_reserved"
        req.funds_reserved_at = timezone.now()
        req.ledger_reference = ledger_ref
        req.save(update_fields=["status", "funds_reserved_at", "ledger_reference"])

    logger.info(
        "payout_request: funds_reserved ref=%s ledger_ref=%s", req.reference, ledger_ref,
    )
    return req


def reject_payout_request(*, request_id: int, rejected_by_id: int, reason: str = ""):
    """
    Reject a pending payout request.

    Only valid from ``pending_approval``.
    """
    from finance.models import StaffPayoutRequest

    with transaction.atomic():
        req = (
            StaffPayoutRequest.objects.select_for_update()
            .filter(pk=request_id)
            .first()
        )
        if not req:
            raise PayoutError("Payout request not found.")
        if req.status != "pending_approval":
            raise PayoutError(f"Cannot reject request in status '{req.status}'.")

        req.status = "rejected"
        req.rejected_by_id = rejected_by_id
        req.rejected_at = timezone.now()
        req.rejection_reason = (reason or "")[:500]
        req.save(update_fields=["status", "rejected_by_id", "rejected_at", "rejection_reason"])

    logger.info(
        "payout_request: rejected ref=%s by=%s reason=%s",
        req.reference, rejected_by_id, reason[:100],
    )
    return req


def cancel_payout_request(*, request_id: int, cancelled_by_id: int, reason: str = ""):
    """
    Cancel a payout request and release any reserved funds.

    Valid from: ``pending_approval``, ``approved``, ``funds_reserved``.
    """
    from finance.models import StaffPayoutRequest
    from finance.services.school_funds import release_reserved_funds

    cancellable = ("pending_approval", "approved", "funds_reserved")

    with transaction.atomic():
        req = (
            StaffPayoutRequest.objects.select_for_update()
            .filter(pk=request_id)
            .first()
        )
        if not req:
            raise PayoutError("Payout request not found.")
        if req.status not in cancellable:
            raise PayoutError(f"Cannot cancel request in status '{req.status}'.")

        # Release reserved funds if they were locked
        if req.status == "funds_reserved" and req.ledger_reference:
            release_reserved_funds(
                school_id=req.school_id,
                amount=req.amount,
                reference=f"CANCEL-{req.reference}",
                description=f"Cancel payout {req.reference}",
                currency=req.currency,
                metadata={
                    "payout_request_id": req.pk,
                    "payout_reference": req.reference,
                    "original_ledger_ref": req.ledger_reference,
                },
            )

        req.status = "cancelled"
        req.cancelled_by_id = cancelled_by_id
        req.cancelled_at = timezone.now()
        req.cancellation_reason = (reason or "")[:500]
        req.save(update_fields=[
            "status", "cancelled_by_id", "cancelled_at", "cancellation_reason",
        ])

    logger.info(
        "payout_request: cancelled ref=%s by=%s reason=%s",
        req.reference, cancelled_by_id, reason[:100],
    )
    return req
