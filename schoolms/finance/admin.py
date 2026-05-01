from django.contrib import admin
from .models import (
    Fee, FeeStructure, FeePayment, PaystackSettlement,
    BankAccount, FeeInstallmentPlan, FeeDiscount,
    PurchaseOrder, PurchaseOrderItem,
    ApprovalWorkflow, WorkflowInstance, FixedAsset,
    Scholarship, ScholarshipAward,
)


@admin.register(Fee)
class FeeAdmin(admin.ModelAdmin):
    list_display = ("student", "school", "amount", "amount_paid", "is_fully_paid", "created_at")
    list_select_related = ("student", "student__user", "school")
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
    list_select_related = ("school",)
    list_filter = ("school",)


@admin.register(FeePayment)
class FeePaymentAdmin(admin.ModelAdmin):
    list_display = ("fee", "amount", "gross_amount", "status", "payment_method", "created_at")
    list_select_related = ("fee", "fee__student", "fee__student__user")
    list_filter = ("status", "payment_method")
    search_fields = ("fee__student__admission_number", "paystack_reference")
    readonly_fields = ("created_at",)


@admin.register(PaystackSettlement)
class PaystackSettlementAdmin(admin.ModelAdmin):
    list_display = ("settlement_id", "school", "settlement_date", "effective_amount", "status", "reconciled", "transactions_count")
    list_filter = ("status", "reconciled", "school")
    search_fields = ("settlement_id", "batch_reference", "school__name")
    readonly_fields = ("settlement_id", "amount", "effective_amount", "settlement_date", "transactions_count", "raw_payload", "created_at")
    date_hierarchy = "settlement_date"
    actions = ["reconcile_selected"]

    @admin.action(description="Reconcile selected settlements against FeePayment records")
    def reconcile_selected(self, request, queryset):
        count = 0
        for s in queryset.filter(reconciled=False):
            s.reconcile()
            count += 1
        self.message_user(request, f"{count} settlement(s) reconciled.")


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ("school", "bank_name", "account_number", "account_type", "currency", "is_primary", "is_active")
    list_filter = ("school", "account_type", "currency", "is_active")
    search_fields = ("school__name", "bank_name", "account_number")
    list_select_related = ("school",)


@admin.register(FeeInstallmentPlan)
class FeeInstallmentPlanAdmin(admin.ModelAdmin):
    list_display = ("fee", "installment_number", "due_date", "amount_due", "amount_paid", "status")
    list_filter = ("status", "school")
    list_select_related = ("fee", "school")
    date_hierarchy = "due_date"


@admin.register(FeeDiscount)
class FeeDiscountAdmin(admin.ModelAdmin):
    list_display = ("fee", "discount_type", "percentage", "fixed_amount", "is_active", "approved_by")
    list_filter = ("discount_type", "is_active", "school")
    list_select_related = ("fee", "school", "approved_by")
    search_fields = ("fee__student__admission_number",)


class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 1
    fields = ("description", "quantity", "unit_price", "total_price", "received_quantity", "inventory_item")
    readonly_fields = ("total_price",)


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("po_number", "school", "supplier_name", "status", "total_amount", "grand_total", "currency", "created_at")
    list_filter = ("status", "school", "currency")
    search_fields = ("po_number", "supplier_name", "school__name")
    list_select_related = ("school", "requested_by")
    readonly_fields = ("po_number", "created_at", "updated_at")
    inlines = [PurchaseOrderItemInline]


@admin.register(ApprovalWorkflow)
class ApprovalWorkflowAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "workflow_type", "is_active", "created_at")
    list_filter = ("workflow_type", "is_active", "school")
    list_select_related = ("school",)
    search_fields = ("name", "school__name")


@admin.register(WorkflowInstance)
class WorkflowInstanceAdmin(admin.ModelAdmin):
    list_display = ("pk", "school", "workflow", "content_type", "object_id", "current_step", "status", "created_at")
    list_filter = ("status", "school", "workflow")
    list_select_related = ("school", "workflow", "initiated_by")
    readonly_fields = ("history", "created_at", "updated_at")


@admin.register(FixedAsset)
class FixedAssetAdmin(admin.ModelAdmin):
    list_display = ("asset_tag", "name", "school", "category", "purchase_cost", "current_book_value", "condition", "is_active")
    list_filter = ("category", "condition", "is_active", "school")
    search_fields = ("asset_tag", "name", "serial_number", "school__name")
    list_select_related = ("school",)
    readonly_fields = ("asset_tag", "annual_depreciation", "created_at", "updated_at")
    date_hierarchy = "purchase_date"
    actions = ["apply_depreciation"]

    @admin.action(description="Apply one year of straight-line depreciation")
    def apply_depreciation(self, request, queryset):
        count = 0
        for asset in queryset.filter(is_active=True):
            asset.apply_annual_depreciation()
            count += 1
        self.message_user(request, f"Depreciation applied to {count} asset(s).")


class ScholarshipAwardInline(admin.TabularInline):
    model = ScholarshipAward
    extra = 0
    fields = ("student", "awarded_amount", "status", "academic_year", "term")
    raw_id_fields = ("student",)
    show_change_link = True


@admin.register(Scholarship)
class ScholarshipAdmin(admin.ModelAdmin):
    list_display = ("name", "scholarship_type", "cycle", "total_budget", "amount_per_award", "is_active", "school")
    list_select_related = ("school",)
    list_filter = ("school", "scholarship_type", "is_active", "cycle")
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")
    inlines = [ScholarshipAwardInline]


@admin.register(ScholarshipAward)
class ScholarshipAwardAdmin(admin.ModelAdmin):
    list_display = ("scholarship", "student", "awarded_amount", "status", "academic_year", "school")
    list_select_related = ("scholarship", "student", "student__user", "school")
    list_filter = ("school", "status", "academic_year")
    search_fields = ("student__user__first_name", "student__user__last_name", "student__admission_number")
    raw_id_fields = ("student",)
    readonly_fields = ("created_at", "updated_at", "approved_at")
    actions = ["activate_awards"]

    @admin.action(description="Activate selected awards")
    def activate_awards(self, request, queryset):
        count = 0
        for award in queryset.filter(status="pending"):
            award.activate(approver=request.user)
            count += 1
        self.message_user(request, f"{count} award(s) activated.")
