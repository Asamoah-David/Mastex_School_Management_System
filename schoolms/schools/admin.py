from django.contrib import admin
from django.db.models import Count
from .models import School, SchoolFeature, SchoolNetwork


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "subdomain", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "subdomain")
    prepopulated_fields = {"subdomain": ("name",)}
    list_editable = ("is_active",)
    ordering = ("-created_at",)


@admin.register(SchoolFeature)
class SchoolFeatureAdmin(admin.ModelAdmin):
    list_display = ("school", "key", "enabled", "updated_at")
    list_filter = ("enabled", "key", "school")
    search_fields = ("school__name", "key")
    ordering = ("school__name", "key")


@admin.register(SchoolNetwork)
class SchoolNetworkAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "owner_email", "annotated_school_count", "created_at")
    search_fields = ("name", "slug", "owner_email")
    filter_horizontal = ("schools",)
    prepopulated_fields = {"slug": ("name",)}

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_school_count=Count("schools", distinct=True))

    @admin.display(description="Schools", ordering="_school_count")
    def annotated_school_count(self, obj):
        return obj._school_count
