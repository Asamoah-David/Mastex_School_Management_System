from django.db import models
from accounts.models import User
from schools.models import School


class InventoryCategory(models.Model):
    """Categories for inventory items"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    class Meta:
        verbose_name_plural = "Inventory Categories"
    
    def __str__(self):
        return self.name


class InventoryItem(models.Model):
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
    
    @property
    def is_low_stock(self):
        return self.quantity <= self.min_quantity


class InventoryTransaction(models.Model):
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
