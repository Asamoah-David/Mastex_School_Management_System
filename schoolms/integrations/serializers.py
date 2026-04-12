from rest_framework import serializers

from operations.models import Expense, StaffLeave
from schools.models import School


class SchoolBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = ("id", "name", "subdomain")


class MeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField(allow_blank=True)
    role = serializers.CharField(allow_blank=True)
    school = serializers.SerializerMethodField()

    def get_school(self, obj):
        s = obj.get("school")
        if s is None:
            return None
        return SchoolBriefSerializer(s).data


class StaffLeaveSerializer(serializers.ModelSerializer):
    staff_username = serializers.CharField(source="staff.username", read_only=True)
    staff_name = serializers.SerializerMethodField()
    reviewed_by_username = serializers.SerializerMethodField()

    class Meta:
        model = StaffLeave
        fields = (
            "id",
            "leave_type",
            "start_date",
            "end_date",
            "reason",
            "status",
            "reviewed_at",
            "review_notes",
            "staff_id",
            "staff_username",
            "staff_name",
            "reviewed_by_id",
            "reviewed_by_username",
            "created_at",
        )
        read_only_fields = fields

    def get_staff_name(self, obj):
        u = obj.staff
        return (u.get_full_name() or "").strip() or u.username

    def get_reviewed_by_username(self, obj):
        rb = obj.reviewed_by
        return rb.username if rb else ""


class ExpenseSerializer(serializers.ModelSerializer):
    category_name = serializers.SerializerMethodField()
    recorded_by_username = serializers.SerializerMethodField()

    def get_category_name(self, obj):
        return obj.category.name if obj.category else ""

    def get_recorded_by_username(self, obj):
        rb = obj.recorded_by
        return rb.username if rb else ""

    class Meta:
        model = Expense
        fields = (
            "id",
            "description",
            "amount",
            "expense_date",
            "vendor",
            "payment_method",
            "receipt_number",
            "category_id",
            "category_name",
            "recorded_by_id",
            "recorded_by_username",
            "approved_by_id",
            "created_at",
        )
        read_only_fields = fields
