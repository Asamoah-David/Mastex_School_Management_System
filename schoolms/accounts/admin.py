from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


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
