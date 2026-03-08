"""
School-scoped operations: attendance, canteen, bus, textbooks.
Each school manages these independently.
"""
from django.db import models
from accounts.models import User
from students.models import Student
from schools.models import School


class StudentAttendance(models.Model):
    STATUS_CHOICES = (("present", "Present"), ("absent", "Absent"), ("late", "Late"), ("excused", "Excused"))
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="present")
    notes = models.CharField(max_length=255, blank=True)
    marked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="marked_attendances")

    class Meta:
        unique_together = ("student", "date")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.student} - {self.date} ({self.status})"


class CanteenItem(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_available = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} - {self.school.name}"


class CanteenPayment(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)  # e.g. "Lunch", "Snack"
    payment_date = models.DateField(auto_now_add=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="canteen_payments_recorded")

    class Meta:
        ordering = ["-payment_date"]

    def __str__(self):
        return f"{self.student} - {self.amount} GHS ({self.payment_date})"


class BusRoute(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)  # e.g. "Route A - North"
    fee_per_term = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.name} - {self.school.name}"


class BusPayment(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    route = models.ForeignKey(BusRoute, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    term_period = models.CharField(max_length=50, blank=True)  # e.g. "Term 1 2025"
    paid = models.BooleanField(default=False)
    payment_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.student} - {self.amount} GHS (Bus)"


class Textbook(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    isbn = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"{self.title} - {self.school.name}"


class TextbookSale(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    textbook = models.ForeignKey(Textbook, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    sale_date = models.DateField(auto_now_add=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="textbook_sales_recorded")

    class Meta:
        ordering = ["-sale_date"]

    def __str__(self):
        return f"{self.student} - {self.textbook.title} x{self.quantity}"
