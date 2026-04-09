from django.db import models
from students.models import Student
from schools.models import School


class Hostel(models.Model):
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


class HostelRoom(models.Model):
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


class HostelAssignment(models.Model):
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

    def __str__(self):
        return f"{self.student} - {self.hostel.name}"


class HostelFee(models.Model):
    """Hostel fee tracking with partial payment support"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE)
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

    def __str__(self):
        return f"{self.student} - {self.hostel.name} - {self.term}"
    
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
        
        self.amount_paid += amount
        self.payment_reference = payment_reference or self.payment_reference
        self.payment_date = timezone.now().date()
        
        # Add to payment history
        payment_record = {
            'amount': str(amount),
            'date': str(self.payment_date),
            'reference': payment_reference or '',
        }
        if self.payment_history is None:
            self.payment_history = []
        self.payment_history.append(payment_record)
        
        # Update paid status
        if self.amount_paid >= self.amount:
            self.paid = True
            self.payment_status = 'completed'
        elif self.amount_paid > 0:
            self.payment_status = 'partial'
        
        self.save()
        return True
