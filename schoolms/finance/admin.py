from django.contrib import admin
from .models import Fee, FeeStructure, FeePayment


@admin.register(Fee)
class FeeAdmin(admin.ModelAdmin):
    list_display = ("student", "school", "amount", "amount_paid", "is_fully_paid", "created_at")
    list_filter = ("school",)
    search_fields = ("student__admission_number", "student__user__username")
    raw_id_fields = ("student",)
    readonly_fields = ("amount_paid", "paystack_payment_id", "paystack_reference", "created_at", "updated_at")
    
    def is_fully_paid(self, obj):
        return obj.is_fully_paid
    is_fully_paid.boolean = True
    is_fully_paid.short_description = "Paid"


@admin.register(FeeStructure)
class FeeStructureAdmin(admin.ModelAdmin):
    list_display = ("name", "amount", "class_name", "term", "school", "is_active")
    list_filter = ("school",)


@admin.register(FeePayment)
class FeePaymentAdmin(admin.ModelAdmin):
    list_display = ("fee", "amount", "status", "payment_method", "created_at")
    list_filter = ("status", "payment_method")
    search_fields = ("fee__student__admission_number", "paystack_reference")
    readonly_fields = ("created_at",)
