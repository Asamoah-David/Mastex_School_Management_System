from django.contrib import admin
from .models import (
    StudentAttendance, TeacherAttendance, AcademicCalendar,
    CanteenItem, CanteenPayment, BusRoute, BusPayment, BusPaymentLedger,
    Textbook, TextbookSale, Announcement, StaffLeave, ActivityLog,
    LibraryBook, LibraryIssue, LibraryFine, Hostel, HostelRoom, HostelAssignment,
    AdmissionApplication, Certificate, StudentIDCard, StaffIDCard,
    ExpenseCategory, Expense, Budget,
    DisciplineIncident, BehaviorPoint, InventoryCategory, InventoryItem,
    PTMeeting, Sport, Club, ExamHall,
)


@admin.register(StudentAttendance)
class StudentAttendanceAdmin(admin.ModelAdmin):
    list_display = ("student", "date", "status", "school")
    list_select_related = ("student", "student__user", "school")
    list_filter = ("school", "status", "date")
    search_fields = ("student__user__first_name", "student__user__last_name", "student__admission_number")
    raw_id_fields = ("student", "marked_by")
    date_hierarchy = "date"


@admin.register(TeacherAttendance)
class TeacherAttendanceAdmin(admin.ModelAdmin):
    list_display = ("teacher", "date", "status", "school")
    list_select_related = ("teacher", "school")
    list_filter = ("school", "status")
    raw_id_fields = ("teacher", "marked_by")
    date_hierarchy = "date"


@admin.register(AcademicCalendar)
class AcademicCalendarAdmin(admin.ModelAdmin):
    list_display = ("title", "event_type", "start_date", "end_date", "school")
    list_select_related = ("school",)
    list_filter = ("school", "event_type")
    search_fields = ("title",)


@admin.register(CanteenItem)
class CanteenItemAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "school", "is_available")
    list_select_related = ("school",)
    list_filter = ("school", "is_available")
    search_fields = ("name",)


@admin.register(CanteenPayment)
class CanteenPaymentAdmin(admin.ModelAdmin):
    list_display = ("student", "amount", "payment_date", "payment_status", "school")
    list_select_related = ("student", "student__user", "school")
    list_filter = ("school", "payment_status")
    raw_id_fields = ("student", "recorded_by")


@admin.register(BusRoute)
class BusRouteAdmin(admin.ModelAdmin):
    list_display = ("name", "fee_per_term", "school")
    list_select_related = ("school",)
    list_filter = ("school",)
    search_fields = ("name",)


@admin.register(BusPayment)
class BusPaymentAdmin(admin.ModelAdmin):
    list_display = ("student", "route", "amount", "term_period", "paid", "school")
    list_select_related = ("student", "student__user", "route", "school")
    list_filter = ("school", "paid")
    raw_id_fields = ("student",)


@admin.register(Textbook)
class TextbookAdmin(admin.ModelAdmin):
    list_display = ("title", "price", "stock", "school")
    list_select_related = ("school",)
    list_filter = ("school",)
    search_fields = ("title", "isbn")


@admin.register(TextbookSale)
class TextbookSaleAdmin(admin.ModelAdmin):
    list_display = ("student", "textbook", "quantity", "amount", "sale_date", "school")
    list_select_related = ("student", "student__user", "textbook", "school")
    list_filter = ("school",)
    raw_id_fields = ("student", "recorded_by")


@admin.register(LibraryBook)
class LibraryBookAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "isbn", "available_copies", "total_copies", "school")
    list_select_related = ("school",)
    list_filter = ("school", "category")
    search_fields = ("title", "author", "isbn")


@admin.register(LibraryIssue)
class LibraryIssueAdmin(admin.ModelAdmin):
    list_display = ("student", "book", "issue_date", "due_date", "return_date", "status")
    list_select_related = ("student", "student__user", "book")
    list_filter = ("school", "status")
    raw_id_fields = ("student", "book", "issued_by")


@admin.register(Hostel)
class HostelAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "total_beds", "school")
    list_select_related = ("school",)
    list_filter = ("school", "type")
    search_fields = ("name",)


@admin.register(HostelRoom)
class HostelRoomAdmin(admin.ModelAdmin):
    list_display = ("room_number", "hostel", "total_beds", "current_occupancy")
    list_select_related = ("hostel", "hostel__school")
    list_filter = ("hostel__school",)
    search_fields = ("room_number",)


@admin.register(HostelAssignment)
class HostelAssignmentAdmin(admin.ModelAdmin):
    list_display = ("student", "room", "start_date", "end_date")
    list_select_related = ("student", "student__user", "room", "room__hostel")
    raw_id_fields = ("student",)


@admin.register(AdmissionApplication)
class AdmissionApplicationAdmin(admin.ModelAdmin):
    list_display = ("public_reference", "first_name", "last_name", "class_applied_for", "status", "applied_at", "school")
    list_select_related = ("school",)
    list_filter = ("school", "status", "class_applied_for")
    search_fields = ("public_reference", "first_name", "last_name", "parent_phone", "parent_email")


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ("student", "certificate_type", "issued_date", "school")
    list_select_related = ("student", "student__user", "school")
    list_filter = ("school", "certificate_type")
    raw_id_fields = ("student",)


@admin.register(StudentIDCard)
class StudentIDCardAdmin(admin.ModelAdmin):
    list_display = ("student", "card_number", "issue_date", "expiry_date", "school")
    list_select_related = ("student", "student__user", "school")
    list_filter = ("school",)
    search_fields = ("card_number", "student__admission_number")
    raw_id_fields = ("student", "created_by")


@admin.register(StaffIDCard)
class StaffIDCardAdmin(admin.ModelAdmin):
    list_display = ("staff", "card_number", "issue_date", "expiry_date", "school")
    list_select_related = ("staff", "school")
    list_filter = ("school",)
    search_fields = ("card_number", "staff__username")
    raw_id_fields = ("staff", "created_by")


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "school")
    list_select_related = ("school",)
    list_filter = ("school",)
    search_fields = ("name",)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("description", "category", "amount", "expense_date", "school")
    list_select_related = ("category", "school")
    list_filter = ("school", "category")
    search_fields = ("description",)
    raw_id_fields = ("recorded_by",)


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ("category", "academic_year", "term", "allocated_amount", "spent_amount", "school")
    list_select_related = ("category", "school")
    list_filter = ("school", "academic_year")


@admin.register(DisciplineIncident)
class DisciplineIncidentAdmin(admin.ModelAdmin):
    list_display = ("student", "incident_type", "incident_date", "severity", "school")
    list_select_related = ("student", "student__user", "school")
    list_filter = ("school", "severity")
    raw_id_fields = ("student", "reported_by")


@admin.register(BehaviorPoint)
class BehaviorPointAdmin(admin.ModelAdmin):
    list_display = ("student", "points", "reason", "awarded_at", "school")
    list_select_related = ("student", "student__user", "school")
    list_filter = ("school", "point_type")
    raw_id_fields = ("student", "awarded_by")


@admin.register(InventoryCategory)
class InventoryCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "school")
    list_select_related = ("school",)
    list_filter = ("school",)


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "quantity", "unit_cost", "school")
    list_select_related = ("category", "school")
    list_filter = ("school", "category", "condition")
    search_fields = ("name",)


@admin.register(PTMeeting)
class PTMeetingAdmin(admin.ModelAdmin):
    list_display = ("title", "meeting_date", "school")
    list_select_related = ("school",)
    list_filter = ("school",)
    search_fields = ("title",)


@admin.register(Sport)
class SportAdmin(admin.ModelAdmin):
    list_display = ("name", "school")
    list_select_related = ("school",)
    list_filter = ("school",)


@admin.register(Club)
class ClubAdmin(admin.ModelAdmin):
    list_display = ("name", "school")
    list_select_related = ("school",)
    list_filter = ("school",)


@admin.register(ExamHall)
class ExamHallAdmin(admin.ModelAdmin):
    list_display = ("name", "rows", "seats_per_row", "school")
    list_select_related = ("school",)
    list_filter = ("school",)


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "school", "target_audience", "is_pinned", "created_at")
    list_select_related = ("school",)
    list_filter = ("school", "target_audience", "is_pinned")
    search_fields = ("title", "content")


@admin.register(StaffLeave)
class StaffLeaveAdmin(admin.ModelAdmin):
    list_display = ("staff", "leave_type", "start_date", "end_date", "status", "school")
    list_select_related = ("staff", "school")
    list_filter = ("school", "status")
    raw_id_fields = ("staff", "reviewed_by")


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("action", "user", "school", "created_at")
    list_select_related = ("user", "school")
    list_filter = ("school", "action")
    search_fields = ("action", "user__username")
    raw_id_fields = ("user",)


class BusPaymentLedgerInline(admin.TabularInline):
    model = BusPaymentLedger
    extra = 0
    readonly_fields = ("amount", "payment_reference", "payment_date", "recorded_by")
    can_delete = False


@admin.register(BusPaymentLedger)
class BusPaymentLedgerAdmin(admin.ModelAdmin):
    list_display = ("bus_payment", "amount", "payment_reference", "payment_date", "recorded_by")
    list_select_related = ("bus_payment", "recorded_by")
    search_fields = ("payment_reference",)
    readonly_fields = ("payment_date",)
    raw_id_fields = ("bus_payment", "recorded_by")


class LibraryFineInline(admin.StackedInline):
    model = LibraryFine
    extra = 0
    readonly_fields = ("created_at", "updated_at")
    can_delete = False


@admin.register(LibraryFine)
class LibraryFineAdmin(admin.ModelAdmin):
    list_display = ("issue", "school", "fine_amount", "amount_paid", "balance_display", "status")
    list_select_related = ("issue", "issue__student", "issue__student__user", "school", "waived_by")
    list_filter = ("school", "status")
    search_fields = (
        "issue__student__admission_number",
        "issue__student__user__first_name",
        "issue__student__user__last_name",
    )
    raw_id_fields = ("issue", "school", "waived_by")
    readonly_fields = ("created_at", "updated_at")
    actions = ["waive_selected_fines"]

    def balance_display(self, obj):
        return obj.balance
    balance_display.short_description = "Balance"

    @admin.action(description="Waive selected library fines")
    def waive_selected_fines(self, request, queryset):
        count = 0
        for fine in queryset.exclude(status__in=["paid", "waived"]):
            fine.waive(user=request.user, reason="Bulk waiver via admin")
            count += 1
        self.message_user(request, f"{count} fine(s) waived.")
