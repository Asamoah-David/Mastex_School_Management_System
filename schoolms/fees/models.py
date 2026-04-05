from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class SubscriptionPlan(models.Model):
    """Subscription plans for schools."""
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_days = models.IntegerField(help_text="Duration in days")
    max_students = models.IntegerField(default=100)
    max_staff = models.IntegerField(default=10)
    features = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class SchoolSubscription(models.Model):
    """School subscription tracking."""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]
    
    school = models.OneToOneField('schools.School', on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    auto_renew = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.school} - {self.plan}"


class PaymentReminder(models.Model):
    """Fee payment reminders."""
    REMINDER_TYPE_CHOICES = [
        ('due', 'Due'),
        ('overdue', 'Overdue'),
        ('receipt', 'Receipt'),
    ]
    
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE, related_name='payment_reminders')
    fee_invoice = models.ForeignKey('finance.FeeInvoice', on_delete=models.CASCADE, related_name='reminders')
    reminder_type = models.CharField(max_length=20, choices=REMINDER_TYPE_CHOICES)
    reminder_date = models.DateTimeField()
    sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-reminder_date']

    def __str__(self):
        return f"{self.student} - {self.reminder_type}"