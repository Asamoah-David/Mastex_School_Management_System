"""Signals that populate operations.ActivityLog and keep denormalised fields in sync."""

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db.models import F, Sum
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from operations.activity import client_ip_from_request, log_school_activity


@receiver(user_logged_in)
def activity_log_login(sender, request, user, **kwargs):
    log_school_activity(
        user=user,
        action="login",
        details="Signed in successfully.",
        ip=client_ip_from_request(request),
    )


@receiver(user_logged_out)
def activity_log_logout(sender, request, user, **kwargs):
    u = user if user is not None and getattr(user, "pk", None) else None
    log_school_activity(
        user=u,
        action="logout",
        details="Signed out.",
        ip=client_ip_from_request(request),
    )


def _sync_room_occupancy(room):
    """Recount active assignments for a room and update current_occupancy."""
    if room is None:
        return
    try:
        from operations.models.hostel import HostelAssignment
        count = HostelAssignment.objects.filter(room=room, is_active=True).count()
        if room.current_occupancy != count:
            room.__class__.objects.filter(pk=room.pk).update(current_occupancy=count)
    except Exception:
        pass


@receiver(post_save, sender="operations.HostelAssignment")
def hostel_assignment_saved(sender, instance, **kwargs):
    if instance.end_date and instance.end_date < timezone.now().date() and instance.is_active:
        instance.__class__.objects.filter(pk=instance.pk).update(is_active=False)
        instance.is_active = False
    _sync_room_occupancy(instance.room)


@receiver(post_delete, sender="operations.HostelAssignment")
def hostel_assignment_deleted(sender, instance, **kwargs):
    _sync_room_occupancy(instance.room)


@receiver(post_save, sender="students.Student")
def sync_student_class_name(sender, instance, **kwargs):
    """Keep Student.class_name in sync with school_class.name when school_class is set."""
    if instance.school_class_id and instance.school_class:
        expected = instance.school_class.name
        if instance.class_name != expected:
            instance.__class__.objects.filter(pk=instance.pk).update(class_name=expected)


# ---------------------------------------------------------------------------
# Fix 2: InventoryTransaction → InventoryItem.quantity
# ---------------------------------------------------------------------------

@receiver(post_save, sender="operations.InventoryTransaction")
def inventory_transaction_update_stock(sender, instance, created, **kwargs):
    """Increment/decrement InventoryItem.quantity by the signed transaction quantity."""
    if not created:
        return
    try:
        from operations.models.inventory import InventoryItem
        InventoryItem.objects.filter(pk=instance.item_id).update(
            quantity=F("quantity") + instance.quantity
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Fix 4: Expense save → Budget.spent_amount recalculation
# ---------------------------------------------------------------------------

def _refresh_budget_spent(budget_id):
    """Recompute Budget.spent_amount from linked approved/paid Expense rows."""
    try:
        from operations.models.finance import Budget, Expense
        total = (
            Expense.objects.filter(
                budget_id=budget_id,
                status__in=["approved", "paid"],
            ).aggregate(t=Sum("amount"))["t"]
            or 0
        )
        Budget.objects.filter(pk=budget_id).update(spent_amount=total)
    except Exception:
        pass


@receiver(post_save, sender="operations.Expense")
@receiver(post_delete, sender="operations.Expense")
def expense_update_budget_spent(sender, instance, **kwargs):
    """Keep Budget.spent_amount accurate whenever an Expense is saved or deleted."""
    if getattr(instance, "budget_id", None):
        _refresh_budget_spent(instance.budget_id)
