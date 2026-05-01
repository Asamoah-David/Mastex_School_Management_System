"""
Class Supply / Contribution Tracker
School creates a supply request per class; teachers track which students have brought items.
"""
from __future__ import annotations

from django.db import models
from django.utils import timezone

from core.tenancy import SchoolScopedModel
from schools.models import School


class ClassSupplyRequest(SchoolScopedModel):
    """A supply drive for a specific class (e.g. 'Term 1 Supplies — Form 2A')."""

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="supply_requests")
    school_class = models.ForeignKey(
        "students.SchoolClass", on_delete=models.CASCADE, related_name="supply_requests",
    )
    title = models.CharField(max_length=200, help_text="e.g. Term 1 Classroom Supplies")
    academic_year = models.CharField(max_length=20, blank=True, help_text="e.g. 2024/2025")
    description = models.TextField(blank=True, help_text="Additional instructions to parents")
    deadline = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notify_parents = models.BooleanField(
        default=True, help_text="Send in-app notification to parents when created",
    )
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_supply_requests",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "school_class", "is_active"], name="idx_supplyreq_school_class"),
        ]

    def __str__(self):
        return f"{self.title} — {self.school_class.name}"

    @property
    def total_items(self):
        return self.items.count()

    @property
    def is_overdue(self):
        if not self.deadline:
            return False
        return timezone.now().date() > self.deadline


class ClassSupplyItem(models.Model):
    """One line item in a supply request (e.g. Broom × 1, Soap × 2)."""

    UNIT_CHOICES = (
        ("piece", "Piece"),
        ("pack", "Pack"),
        ("roll", "Roll"),
        ("bottle", "Bottle"),
        ("box", "Box"),
        ("bag", "Bag"),
        ("pair", "Pair"),
        ("litre", "Litre"),
        ("other", "Other"),
    )

    request = models.ForeignKey(ClassSupplyRequest, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=150, help_text="e.g. Broom, Soap, Toilet Tissue")
    quantity_per_student = models.PositiveSmallIntegerField(
        default=1, help_text="How many units each student is expected to bring",
    )
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default="piece")
    notes = models.CharField(max_length=255, blank=True, help_text="e.g. 'Size A4', 'Brand does not matter'")
    order = models.PositiveSmallIntegerField(default=0, help_text="Display order")

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return f"{self.name} × {self.quantity_per_student} {self.unit}"

    def brought_count(self):
        """Number of students who have brought this item."""
        return self.contributions.values("student").distinct().count()

    def pending_count(self):
        """Students in the class who have NOT contributed this item."""
        total = self.request.school_class.students.filter(
            deleted_at__isnull=True, status="active"
        ).count()
        return max(0, total - self.brought_count())


class StudentSupplyContribution(models.Model):
    """Records that a specific student brought a specific supply item."""

    item = models.ForeignKey(ClassSupplyItem, on_delete=models.CASCADE, related_name="contributions")
    student = models.ForeignKey(
        "students.Student", on_delete=models.CASCADE, related_name="supply_contributions",
    )
    quantity_brought = models.PositiveSmallIntegerField(default=1)
    brought_date = models.DateField(default=timezone.now)
    recorded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="recorded_supply_contributions",
    )
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-brought_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["item", "student"],
                name="uniq_supply_contrib_item_stu",
            ),
        ]
        indexes = [
            models.Index(fields=["item", "student"], name="idx_supply_contrib_item_stu"),
        ]

    def __str__(self):
        return f"{self.student} — {self.item.name}"
