from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, PasswordResetRequest
from .hr_models import (
    StaffContract, StaffPayrollPayment, StaffRoleChangeLog, StaffTeachingAssignment,
    LeavePolicy, LeaveBalance, PayrollRun, StaffPerformanceReview,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Django Admin User Management
    
    UNDERSTANDING THE FIELDS:
    
    1. ROLE (Application Role) - The user's role in the school system:
       - super_admin: Platform administrator (full system access)
       - school_admin: School administrator (manage their school)
       - teacher: Teaching staff (upload results, mark attendance)
       - student: Student account (view portal, results)
       - parent: Parent account (view children info)
       - staff: Non-teaching staff (admin assistants, etc.)
    
    2. IS STAFF - Django Admin Access:
       - True = Can access Django admin panel
       - False = Cannot access Django admin (recommended for most users)
       
       NOTE: role='staff' is DIFFERENT from is_staff=True
       - role='staff' = application role (non-teaching employee)
       - is_staff=True = can access Django admin interface
    
    3. IS ACTIVE - Login Status:
       - True = Account is active (can login)
       - False = Account is disabled (cannot login)
    """
    
    list_display = (
        "username", 
        "get_name_display", 
        "role", 
        "school", 
        "is_staff",  
        "is_active",  
        "date_joined"
    )
    
    list_filter = (
        "role", 
        "parent_type", 
        "is_staff",      
        "is_active",     
        "school"
    )
    
    search_fields = (
        "username", 
        "email", 
        "first_name", 
        "last_name", 
        "phone"
    )
    
    ordering = ("-date_joined",)
    filter_horizontal = ('groups', 'user_permissions',)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal Info", {"fields": ("first_name", "last_name", "email")}),
        ("📋 Application Role", {
            "fields": ("role", "school", "phone", "parent_type"),
        }),
        ("🔐 Django Admin Access", {
            "fields": ("is_staff", "is_active"),
            "description": "is_staff: Can access Django admin panel | is_active: Can login to system"
        }),
        ("⚡ Permissions", {
            "fields": ("is_super_admin", "user_permissions", "groups"),
        }),
        ("📅 Important Dates", {"fields": ("last_login", "date_joined")}),
    )
    
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "password1", "password2"),
        }),
        ("Personal Info", {"fields": ("first_name", "last_name", "email")}),
        ("📋 Application Role", {"fields": ("role", "school", "phone", "parent_type")}),
        ("🔐 Django Admin Access", {"fields": ("is_staff", "is_active")}),
        ("⚡ Permissions", {"fields": ("is_super_admin", "user_permissions", "groups")}),
    )
    
    list_editable = ("role", "is_staff", "is_active")
    
    actions = [
        "activate_users", 
        "deactivate_users", 
        "grant_admin_access",
        "revoke_admin_access",
        "change_to_teacher", 
        "change_to_parent",
        "change_to_staff"
    ]

    @admin.action(description="✓ Activate selected users (can login)")
    def activate_users(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} user(s) can now login.")

    @admin.action(description="✗ Deactivate selected users (cannot login)")
    def deactivate_users(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} user(s) can no longer login.")

    @admin.action(description="🔓 Grant Django admin access")
    def grant_admin_access(self, request, queryset):
        count = queryset.update(is_staff=True)
        self.message_user(request, f"{count} user(s) can now access Django admin.")

    @admin.action(description="🔒 Revoke Django admin access")
    def revoke_admin_access(self, request, queryset):
        count = queryset.update(is_staff=False)
        self.message_user(request, f"{count} user(s) no longer have Django admin access.")

    @admin.action(description="👨‍🏫 Change role to Teacher")
    def change_to_teacher(self, request, queryset):
        count = queryset.update(role="teacher")
        self.message_user(request, f"{count} user(s) changed to Teacher role.")

    @admin.action(description="👨‍👩‍👧 Change role to Parent")
    def change_to_parent(self, request, queryset):
        count = queryset.update(role="parent")
        self.message_user(request, f"{count} user(s) changed to Parent role.")

    @admin.action(description="👤 Change role to Staff (non-teaching)")
    def change_to_staff(self, request, queryset):
        count = queryset.update(role="staff")
        self.message_user(request, f"{count} user(s) changed to Staff role.")
    
    def get_name_display(self, obj):
        return obj.get_full_name() or obj.username
    get_name_display.short_description = "Name"


@admin.register(StaffContract)
class StaffContractAdmin(admin.ModelAdmin):
    list_display = ("user", "school", "contract_type", "job_title", "start_date", "end_date", "status")
    list_filter = ("contract_type", "status", "school")
    search_fields = ("user__username", "user__email", "job_title", "notes")
    raw_id_fields = ("user", "school")


@admin.register(StaffTeachingAssignment)
class StaffTeachingAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "school", "subject", "class_name", "academic_year", "is_active", "effective_from", "effective_until")
    list_filter = ("is_active", "school")
    search_fields = ("user__username", "class_name", "notes")
    raw_id_fields = ("user", "school", "subject")


@admin.register(StaffPayrollPayment)
class StaffPayrollPaymentAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "school",
        "period_label",
        "amount",
        "currency",
        "paid_on",
        "method",
        "paystack_status",
        "paystack_transfer_code",
        "recorded_by",
    )
    list_filter = ("method", "paystack_status", "school", "paid_on")
    search_fields = ("user__username", "period_label", "reference", "notes")
    raw_id_fields = ("user", "school", "recorded_by")


@admin.register(StaffRoleChangeLog)
class StaffRoleChangeLogAdmin(admin.ModelAdmin):
    list_display = ("user", "school", "change_kind", "changed_at", "changed_by", "from_value", "to_value")
    list_filter = ("change_kind", "school")
    search_fields = ("user__username", "from_value", "to_value", "notes")
    raw_id_fields = ("user", "school", "changed_by")


@admin.register(PasswordResetRequest)
class PasswordResetRequestAdmin(admin.ModelAdmin):
    list_display = ("email", "ip_address", "requested_at", "expires_at", "used_at", "user")
    list_filter = ("used_at",)
    search_fields = ("email", "ip_address")
    readonly_fields = ("requested_at",)
    raw_id_fields = ("user",)
    date_hierarchy = "requested_at"


@admin.register(LeavePolicy)
class LeavePolicyAdmin(admin.ModelAdmin):
    list_display = ("school", "leave_type", "days_per_year", "carry_over_max_days", "is_active")
    list_filter = ("leave_type", "is_active", "school")
    search_fields = ("school__name",)


@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = ("user", "school", "leave_type", "academic_year", "allocated_days", "used_days", "carried_over")
    list_filter = ("leave_type", "academic_year", "school")
    search_fields = ("user__username", "user__first_name", "user__last_name", "school__name")
    raw_id_fields = ("user", "school")


@admin.register(PayrollRun)
class PayrollRunAdmin(admin.ModelAdmin):
    list_display = ("school", "period_label", "pay_date", "status", "staff_count", "total_gross", "total_net")
    list_filter = ("status", "school")
    search_fields = ("period_label", "school__name")
    readonly_fields = ("total_gross", "total_net", "total_paye", "total_ssnit", "staff_count", "completed_at", "created_at")
    date_hierarchy = "pay_date"


@admin.register(StaffPerformanceReview)
class StaffPerformanceReviewAdmin(admin.ModelAdmin):
    list_display = ("staff", "school", "review_period", "academic_year", "overall_rating", "is_finalised", "created_at")
    list_filter = ("review_period", "academic_year", "is_finalised", "school")
    search_fields = ("staff__username", "staff__first_name", "staff__last_name", "school__name")
    raw_id_fields = ("staff", "reviewer")
    readonly_fields = ("created_at", "updated_at", "finalised_at")
