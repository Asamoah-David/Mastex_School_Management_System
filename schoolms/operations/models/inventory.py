from django.db import models
from accounts.models import User
from schools.models import School
from django.core.exceptions import ValidationError
from core.tenancy import SchoolScopedModel


class InventoryCategory(SchoolScopedModel):
    """Categories for inventory items"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Inventory Categories"
        constraints = [
            # Per-school uniqueness so admins cannot silently create duplicate
            # categories that split inventory counts and reporting.
            models.UniqueConstraint(
                fields=["school", "name"],
                name="uniq_invcategory_school_name",
            ),
        ]

    def __str__(self):
        return self.name


class InventoryItem(SchoolScopedModel):
    """School inventory items"""
    CONDITION_CHOICES = (
        ('new', 'New'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
        ('damaged', 'Damaged'),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    category = models.ForeignKey(InventoryCategory, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=0)
    min_quantity = models.PositiveIntegerField(default=5)  # Alert when below this
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='new')
    location = models.CharField(max_length=100, blank=True)  # Where it's stored
    description = models.TextField(blank=True)
    serial_number = models.CharField(max_length=100, blank=True)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["name"]
    
    def __str__(self):
        return f"{self.name} ({self.quantity})"

    def clean(self):
        super().clean()
        if self.category_id and self.school_id and getattr(self.category, "school_id", None) != self.school_id:
            raise ValidationError({"category": "Category must belong to the same school as the item."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    
    @property
    def is_low_stock(self):
        return self.quantity <= self.min_quantity


class InventoryTransaction(SchoolScopedModel):
    """Track inventory movements (additions, removals)"""
    TRANSACTION_TYPES = (
        ('purchase', 'Purchase'),
        ('usage', 'Usage'),
        ('damage', 'Damage'),
        ('adjustment', 'Adjustment'),
        ('return', 'Return'),
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    quantity = models.IntegerField()  # Can be negative for usage
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-created_at"]
    
    def __str__(self):
        return f"{self.transaction_type} - {self.item.name} ({self.quantity})"

    def clean(self):
        super().clean()
        if self.item_id and self.school_id and getattr(self.item, "school_id", None) != self.school_id:
            raise ValidationError({"item": "Item must belong to the same school as the transaction."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
