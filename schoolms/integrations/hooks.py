"""Schedule webhook notifications after DB commits (operations domain)."""

from __future__ import annotations

from django.db import transaction

from integrations.webhook_delivery import deliver_school_event


def schedule_staff_leave_webhook(leave_id: int) -> None:
    def _run():
        from operations.models import StaffLeave

        try:
            leave = StaffLeave.objects.select_related("school", "staff", "reviewed_by").get(pk=leave_id)
        except StaffLeave.DoesNotExist:
            return
        staff = leave.staff
        payload = {
            "id": leave.pk,
            "status": leave.status,
            "leave_type": leave.leave_type,
            "start_date": str(leave.start_date),
            "end_date": str(leave.end_date),
            "staff_id": staff.pk,
            "staff_username": staff.username,
            "staff_name": staff.get_full_name() or staff.username,
            "reviewed_by_id": leave.reviewed_by_id,
            "reviewed_at": leave.reviewed_at.isoformat() if leave.reviewed_at else None,
            "review_notes": leave.review_notes or "",
        }
        deliver_school_event(leave.school_id, "staff_leave.updated", payload)

    transaction.on_commit(_run)


def schedule_expense_webhook(expense_id: int, *, created: bool) -> None:
    def _run():
        from operations.models import Expense

        try:
            exp = Expense.objects.select_related("school", "category", "recorded_by", "approved_by").get(
                pk=expense_id
            )
        except Expense.DoesNotExist:
            return
        payload = {
            "id": exp.pk,
            "created": created,
            "description": exp.description,
            "amount": str(exp.amount),
            "expense_date": str(exp.expense_date),
            "vendor": exp.vendor,
            "payment_method": exp.payment_method,
            "category": exp.category.name if exp.category else "",
            "recorded_by_id": exp.recorded_by_id,
            "approved_by_id": exp.approved_by_id,
        }
        deliver_school_event(exp.school_id, "expense.updated", payload)

    transaction.on_commit(_run)
