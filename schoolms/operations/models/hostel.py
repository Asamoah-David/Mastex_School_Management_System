from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from students.models import Student
from schools.models import School
from accounts.models import User
from core.tenancy import SchoolScopedModel


class Hostel(SchoolScopedModel):
    """Hostel/Dormitory information"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=50)  # Boys, Girls, Mixed
    total_beds = models.PositiveIntegerField(default=50)
    warden_name = models.CharField(max_length=100, blank=True)
    warden_phone = models.CharField(max_length=20, blank=True)
    fee_per_term = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.name} ({self.type})"


class HostelRoom(SchoolScopedModel):
    """Individual rooms in hostel"""
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name="rooms")
    room_number = models.CharField(max_length=20)
    floor = models.PositiveIntegerField(default=1)
    total_beds = models.PositiveIntegerField(default=4)
    current_occupancy = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("hostel", "room_number")

    def __str__(self):
        return f"{self.hostel.name} - Room {self.room_number}"


class HostelAssignment(SchoolScopedModel):
    """Track student hostel assignments."""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE)
    room = models.ForeignKey(HostelRoom, on_delete=models.SET_NULL, null=True, blank=True)
    bed_number = models.CharField(max_length=10, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]
        indexes = [
            models.Index(fields=["school", "student", "is_active"], name="idx_hostelasn_sch_stu"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["student"],
                condition=models.Q(is_active=True),
                name="uniq_hostelasn_one_active_per_student",
            ),
        ]

    def __str__(self):
        return f"{self.student} - {self.hostel.name}"

    def clean(self):
        super().clean()
        if self.school_id and self.student_id:
            s_school = getattr(self.student, "school_id", None)
            if s_school is not None and s_school != self.school_id:
                raise ValidationError({"student": "Student must belong to the same school as the hostel assignment."})
        if self.school_id and self.hostel_id:
            h_school = getattr(self.hostel, "school_id", None)
            if h_school is not None and h_school != self.school_id:
                raise ValidationError({"hostel": "Hostel must belong to the same school as the assignment."})
        if self.hostel_id and self.room_id:
            if self.room.hostel_id != self.hostel_id:
                raise ValidationError({"room": "Room must belong to the selected hostel."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class HostelFee(SchoolScopedModel):
    """Hostel fee tracking with partial payment support"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE)
    term_fk = models.ForeignKey(
        "academics.Term",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="hostel_fees",
        help_text="Structured term FK. Prefer this over the legacy term CharField.",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Track partial payments
    term = models.CharField(max_length=50)  # e.g., "Term 1 2025"
    paid = models.BooleanField(default=False)
    payment_date = models.DateField(null=True, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)  # Paystack reference
    payment_status = models.CharField(max_length=20, default='pending')  # pending, partial, completed, failed
    
    # Track payment history
    payment_history = models.JSONField(default=list, blank=True)  # List of partial payments

    class Meta:
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["payment_reference"],
                condition=models.Q(payment_reference__isnull=False)
                & ~models.Q(payment_reference=""),
                name="uniq_hostelfee_payment_reference_nonempty",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "student", "-id"], name="idx_hostelfee_school_student"),
            models.Index(fields=["school", "payment_status", "-id"], name="idx_hostelfee_school_status"),
        ]

    def __str__(self):
        return f"{self.student} - {self.hostel.name} - {self.term}"

    def clean(self):
        super().clean()
        if self.school_id and self.student_id:
            s_school = getattr(self.student, "school_id", None)
            if s_school is not None and s_school != self.school_id:
                raise ValidationError({"student": "Student must belong to the same school as the hostel fee."})
        if self.school_id and self.hostel_id:
            h_school = getattr(self.hostel, "school_id", None)
            if h_school is not None and h_school != self.school_id:
                raise ValidationError({"hostel": "Hostel must belong to the same school as the fee."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def balance(self):
        """Calculate remaining balance"""
        return max(self.amount - self.amount_paid, 0)
    
    @property
    def payment_status_display(self):
        """Return human-readable payment status"""
        if self.paid:
            return "Paid"
        elif self.amount_paid > 0:
            return f"Partial ({self.amount_paid}/{self.amount})"
        else:
            return "Unpaid"
    
    @property
    def percentage_paid(self):
        """Calculate percentage paid"""
        if self.amount == 0:
            return 0
        return int((self.amount_paid / self.amount) * 100)
    
    def add_payment(self, amount, payment_reference=None, recorded_by=None):
        """Add a partial payment and update status"""
        from django.utils import timezone

        amt = Decimal(str(amount or 0))
        if amt <= 0:
            return False

        with transaction.atomic():
            fee = HostelFee.objects.select_for_update().get(pk=self.pk)

            fee.amount_paid = (fee.amount_paid or Decimal("0")) + amt
            if payment_reference and not fee.payment_reference:
                fee.payment_reference = payment_reference
            fee.payment_date = timezone.now().date()

            payment_record = {
                "amount": str(amt),
                "date": str(fee.payment_date),
                "reference": payment_reference or "",
            }
            if fee.payment_history is None:
                fee.payment_history = []
            fee.payment_history.append(payment_record)

            # New immutable payment ledger row (kept alongside legacy JSON
            # history for backward compatibility with existing templates/views).
            if payment_reference:
                HostelFeePayment.objects.get_or_create(
                    payment_reference=payment_reference,
                    defaults={
                        "hostel_fee": fee,
                        "amount": amt,
                        "payment_date": timezone.now(),
                        "recorded_by": recorded_by if getattr(recorded_by, "is_authenticated", False) else None,
                    },
                )
            else:
                HostelFeePayment.objects.create(
                    hostel_fee=fee,
                    amount=amt,
                    payment_date=timezone.now(),
                    recorded_by=recorded_by if getattr(recorded_by, "is_authenticated", False) else None,
                )

            if fee.amount_paid >= (fee.amount or Decimal("0")):
                fee.paid = True
                fee.payment_status = 'completed'
            elif fee.amount_paid > 0:
                fee.payment_status = 'partial'

            fee.save(update_fields=[
                "amount_paid",
                "payment_reference",
                "payment_date",
                "payment_history",
                "paid",
                "payment_status",
            ])

            # Keep instance in sync
            self.amount_paid = fee.amount_paid
            self.payment_reference = fee.payment_reference
            self.payment_date = fee.payment_date
            self.payment_history = fee.payment_history
            self.paid = fee.paid
            self.payment_status = fee.payment_status

        return True


class HostelFeePayment(SchoolScopedModel):
    """Immutable ledger rows for hostel fee payments (partial/full)."""

    hostel_fee = models.ForeignKey(HostelFee, on_delete=models.CASCADE, related_name="payment_entries")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_reference = models.CharField(max_length=100, blank=True, default="", db_index=True)
    payment_date = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["-payment_date", "-id"]
        indexes = [
            models.Index(fields=["hostel_fee", "payment_date"], name="idx_hostelfeepay_fee_date"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name="chk_hostelfeepay_amount_positive",
            ),
            models.UniqueConstraint(
                fields=["payment_reference"],
                condition=~models.Q(payment_reference=""),
                name="uniq_hostelfeepay_reference_nonempty",
            ),
        ]

    def __str__(self):
        return f"{self.hostel_fee_id} - {self.amount} ({self.payment_reference or 'manual'})"


# ---------------------------------------------------------------------------
# Signals: keep HostelRoom.current_occupancy accurate
# ---------------------------------------------------------------------------

def _refresh_room_occupancy(room_id):
    """Recalculate and save current_occupancy for the given room PK."""
    if not room_id:
        return
    count = HostelAssignment.objects.filter(room_id=room_id, is_active=True).count()
    HostelRoom.objects.filter(pk=room_id).update(current_occupancy=count)


@receiver(post_save, sender=HostelAssignment)
def _hostel_assignment_post_save(sender, instance, **kwargs):
    _refresh_room_occupancy(instance.room_id)


@receiver(post_delete, sender=HostelAssignment)
def _hostel_assignment_post_delete(sender, instance, **kwargs):
    _refresh_room_occupancy(instance.room_id)
