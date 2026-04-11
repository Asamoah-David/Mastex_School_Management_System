from django.urls import path
from django.views.generic import RedirectView
from . import views
from . import payment_views
from . import export_views
from . import qr_views
from . import advanced_views

app_name = "operations"

urlpatterns = [
    # ==================== EXPORT VIEWS ====================
    path("export/students/", export_views.export_students, name="export_students"),
    path("export/staff/", export_views.export_staff, name="export_staff"),
    path("export/staff-payroll/", export_views.export_staff_payroll_school, name="export_staff_payroll"),
    path("export/attendance/", export_views.export_attendance, name="export_attendance"),
    path("export/expenses/", export_views.export_expenses, name="export_expenses"),
    path("export/fees/", export_views.export_fees, name="export_fees"),
    path("export/library-books/", export_views.export_library_books, name="export_library_books"),
    path("export/library-issues/", export_views.export_library_issues, name="export_library_issues"),
    path("export/discipline/", export_views.export_discipline, name="export_discipline"),
    path("export/inventory/", export_views.export_inventory, name="export_inventory"),
    path("export/announcements/", export_views.export_announcements, name="export_announcements"),
    path("export/admissions/", export_views.export_admissions, name="export_admissions"),
    path("export/health-records/", export_views.export_health_records, name="export_health_records"),
    path("export/budgets/", export_views.export_budgets, name="export_budgets"),
    path("export/online-exams/", export_views.export_online_exams, name="export_online_exams"),
    path("export/all/", export_views.export_all_data, name="export_all_data"),
    
    # Payment Exports with Day/Month Filtering
    path("export/canteen-payments/", export_views.export_canteen_payments, name="export_canteen_payments"),
    path("export/bus-payments/", export_views.export_bus_payments, name="export_bus_payments"),
    path("export/textbook-sales/", export_views.export_textbook_sales, name="export_textbook_sales"),
    path("export/hostel-fees/", export_views.export_hostel_fees, name="export_hostel_fees"),
    path("export/all-payments/", export_views.export_all_payments, name="export_all_payments"),
    
    # Payment Dashboard
    path("payments/", payment_views.payment_dashboard, name="payment_dashboard"),
    path("payments/student/<int:student_id>/", payment_views.student_payment_history, name="student_payment_history"),
    path("payments/record/", payment_views.record_payment, name="record_payment"),
    path("payments/my/", payment_views.my_payments, name="my_payments"),
    path("payments/receipt/<str:payment_type>/<int:payment_id>/", payment_views.generate_receipt, name="generate_receipt"),
    
    # Online Payment Integration (Paystack)
    path("payments/initiate/", payment_views.initiate_online_payment, name="initiate_online_payment"),
    path("payments/paystack/callback/", payment_views.paystack_callback, name="paystack_callback"),
    path("payments/paystack/webhook/", payment_views.paystack_webhook, name="paystack_webhook"),
    path("payments/send-reminder/", payment_views.send_payment_reminder, name="send_payment_reminder"),
    path("payments/cancel-pending/", payment_views.cancel_pending_payment, name="cancel_pending_payment"),

    # Student Attendance
    path("attendance/", views.attendance_list, name="attendance_list"),
    path("attendance/mark/", views.attendance_mark, name="attendance_mark"),
    path("attendance/edit/<int:pk>/", views.attendance_edit, name="attendance_edit"),
    path("attendance/delete/<int:pk>/", views.attendance_delete, name="attendance_delete"),
    
    # QR Code Attendance System
    path("attendance/qr-scanner/", qr_views.qr_attendance_scanner, name="qr_attendance_scanner"),
    path("attendance/qr-class/<str:class_name>/", qr_views.qr_attendance_class, name="qr_attendance_class"),
    path("attendance/qr-mark/", qr_views.qr_mark_attendance, name="qr_mark_attendance"),
    path("attendance/qr-summary/", qr_views.attendance_qr_summary, name="attendance_qr_summary"),
    path("attendance/qr-codes/<str:class_name>/", qr_views.bulk_qr_codes, name="bulk_qr_codes"),
    path("attendance/student-qr/<int:student_id>/", qr_views.student_qr_preview, name="student_qr_preview"),
    
    # Teacher Attendance
    path("teacher-attendance/", views.teacher_attendance_list, name="teacher_attendance_list"),
    path("teacher-attendance/mark/", views.teacher_attendance_mark, name="teacher_attendance_mark"),
    path("teacher-attendance/edit/<int:pk>/", views.teacher_attendance_edit, name="teacher_attendance_edit"),
    
    # Academic Calendar
    path("calendar/", views.calendar_list, name="calendar"),
    path("calendar/create/", views.calendar_create, name="calendar_create"),
    path("calendar/edit/<int:pk>/", views.calendar_edit, name="calendar_edit"),
    path("calendar/delete/<int:pk>/", views.calendar_delete, name="calendar_delete"),
    
    # Canteen (Student/Parent Portal with Paystack)
    path("canteen/", views.canteen_list, name="canteen_list"),
    path("canteen/create/", views.canteen_create, name="canteen_create"),
    path("canteen/payments/", views.canteen_payments, name="canteen_payments"),
    path("canteen/delete/<int:pk>/", views.canteen_item_delete, name="canteen_item_delete"),
    path("canteen/my/", payment_views.canteen_my, name="canteen_my"),
    path("canteen/pay/", payment_views.canteen_initiate_payment, name="canteen_initiate_payment"),
    path("canteen/verify/", payment_views.canteen_payment_verify, name="canteen_payment_verify"),
    path("canteen/preorder/", advanced_views.canteen_preorder_page, name="canteen_preorder"),
    path("canteen/preorder/create/", advanced_views.create_preorder, name="canteen_preorder_create"),
    
    # Bus/Transport (Student/Parent Portal with Paystack)
    path("bus/", views.bus_list, name="bus_list"),
    path("bus/create/", views.bus_create, name="bus_create"),
    path("bus/payments/", views.bus_payments, name="bus_payments"),
    path("bus/delete/<int:pk>/", views.bus_route_delete, name="bus_route_delete"),
    path("bus/my/", payment_views.bus_my, name="bus_my"),
    path("bus/pay/", payment_views.bus_initiate_payment, name="bus_initiate_payment"),
    path("bus/verify/", payment_views.bus_payment_verify, name="bus_payment_verify"),
    
    # Textbooks (Student/Parent Portal with Paystack)
    path("textbooks/", views.textbook_list, name="textbook_list"),
    path("textbooks/create/", views.textbook_create, name="textbook_create"),
    path("textbooks/sales/", views.textbook_sales, name="textbook_sales"),
    path("textbooks/delete/<int:pk>/", views.textbook_delete, name="textbook_delete"),
    path("textbooks/my/", payment_views.textbook_my, name="textbook_my"),
    path("textbooks/pay/", payment_views.textbook_initiate_payment, name="textbook_initiate_payment"),
    path("textbooks/verify/", payment_views.textbook_payment_verify, name="textbook_payment_verify"),
    
    # Hostel (Student/Parent Portal with Paystack) — canonical page is hostels/my/
    path(
        "hostel/my/",
        RedirectView.as_view(pattern_name="operations:hostel_my", permanent=False),
    ),
    path("hostel/pay/", payment_views.hostel_initiate_payment, name="hostel_initiate_payment"),
    path("hostel/verify/", payment_views.hostel_payment_verify, name="hostel_payment_verify"),

    # Announcements
    path("announcements/", views.announcement_list, name="announcement_list"),
    path("announcements/create/", views.announcement_create, name="announcement_create"),
    path("announcements/delete/<int:pk>/", views.announcement_delete, name="announcement_delete"),

    # Staff Leave
    path("staff-leave/", views.staff_leave_list, name="staff_leave_list"),
    path("staff-leave/create/", views.staff_leave_create, name="staff_leave_create"),
    path("staff-leave/<int:pk>/review/", views.staff_leave_review, name="staff_leave_review"),

    # Activity Log
    path("activity-log/", views.activity_log_list, name="activity_log_list"),

    # Staff services hub (canteen, transport, textbooks, hostel, library, fees)
    path("services/", views.services_hub, name="services_hub"),

    # Library
    path("library/", views.library_catalog, name="library_catalog"),
    path("library/manage/", views.library_manage, name="library_manage"),
    path("library/books/create/", views.library_book_create, name="library_book_create"),
    path("library/books/<int:pk>/delete/", views.library_book_delete, name="library_book_delete"),
    path("library/issues/", views.library_issues, name="library_issues"),
    path("library/issues/create/", views.library_issue_create, name="library_issue_create"),
    path("library/issues/<int:pk>/return/", views.library_issue_return, name="library_issue_return"),
    path("library/my-issues/", views.library_my_issues, name="library_my_issues"),

    # Hostel
    path("hostels/", views.hostel_list, name="hostel_list"),
    path("hostels/create/", views.hostel_create, name="hostel_create"),
    path("hostels/<int:pk>/rooms/", views.hostel_rooms, name="hostel_rooms"),
    path("hostels/<int:pk>/rooms/create/", views.hostel_room_create, name="hostel_room_create"),
    path("hostels/rooms/<int:pk>/edit/", views.hostel_room_edit, name="hostel_room_edit"),
    path("hostels/assignments/", views.hostel_assignments, name="hostel_assignments"),
    path("hostels/assignments/create/", views.hostel_assignment_create, name="hostel_assignment_create"),
    path("hostels/assignments/<int:pk>/end/", views.hostel_assignment_end, name="hostel_assignment_end"),
    path("hostels/fees/", views.hostel_fees, name="hostel_fees"),
    path("hostels/fees/create/", views.hostel_fee_create, name="hostel_fee_create"),
    path("hostels/fees/detail/<int:pk>/", views.hostel_fee_detail, name="hostel_fee_detail"),
    path("hostels/fees/<int:pk>/mark-paid/", views.hostel_fee_mark_paid, name="hostel_fee_mark_paid"),
    path("hostels/my/", views.hostel_my, name="hostel_my"),
    
    # Admission Applications
    path("admission/apply/", views.admission_apply, name="admission_apply"),
    path("admission/list/", views.admission_list, name="admission_list"),
    path("admission/<int:pk>/", views.admission_detail, name="admission_detail"),
    path("admission/<int:pk>/approve/", views.admission_approve, name="admission_approve"),
    path("admission/<int:pk>/reject/", views.admission_reject, name="admission_reject"),
    path("admission/track/", views.admission_track, name="admission_track"),
    
    # Student portal (certificates / ID — not admin lists)
    path("my-certificates/", views.student_my_certificates, name="student_my_certificates"),
    path("my-id-card/", views.student_my_id_card, name="student_my_id_card"),

    # Certificates
    path("certificates/", views.certificate_list, name="certificate_list"),
    path("certificates/create/", views.certificate_create, name="certificate_create"),
    path("certificates/<int:pk>/", views.certificate_view, name="certificate_view"),
    path("certificates/<int:pk>/pdf/", views.certificate_pdf, name="certificate_pdf"),
    path("certificates/<int:pk>/delete/", views.certificate_delete, name="certificate_delete"),
    
    # Expense Tracking
    path("expenses/", views.expense_list, name="expense_list"),
    path("expenses/create/", views.expense_create, name="expense_create"),
    path("expenses/<int:pk>/", views.expense_detail, name="expense_detail"),
    path("expenses/<int:pk>/edit/", views.expense_edit, name="expense_edit"),
    path("expenses/<int:pk>/delete/", views.expense_delete, name="expense_delete"),
    
    # Budget
    path("budgets/", views.budget_list, name="budget_list"),
    path("budgets/create/", views.budget_create, name="budget_create"),
    path("budgets/<int:pk>/edit/", views.budget_edit, name="budget_edit"),
    path("budgets/<int:pk>/delete/", views.budget_delete, name="budget_delete"),
    
    # Expense Categories
    path("expense-categories/", views.expense_category_list, name="expense_category_list"),
    path("expense-categories/create/", views.expense_category_create, name="expense_category_create"),
    
    # Discipline
    path("discipline/", views.discipline_list, name="discipline_list"),
    path("discipline/create/", views.discipline_create, name="discipline_create"),
    path("discipline/<int:pk>/", views.discipline_detail, name="discipline_detail"),
    path("discipline/<int:pk>/delete/", views.discipline_delete, name="discipline_delete"),
    
    # Behavior Points
    path("behavior-points/", views.behavior_points_list, name="behavior_points_list"),
    path("behavior-points/create/", views.behavior_points_create, name="behavior_points_create"),
    
    # Documents
    path("documents/", views.document_list, name="document_list"),
    path("documents/upload/", views.document_upload, name="document_upload"),
    
    # Alumni
    path("alumni/", views.alumni_list, name="alumni_list"),
    path("alumni/create/", views.alumni_create, name="alumni_create"),
    path("alumni/<int:pk>/edit/", views.alumni_edit, name="alumni_edit"),
    path("alumni/<int:pk>/", views.alumni_detail, name="alumni_detail"),
    path("alumni/events/", views.alumni_event_list, name="alumni_event_list"),
    
    # Timetable
    path("timetable/", views.timetable_view, name="timetable_view"),
    path("timetable/create/", views.timetable_create, name="timetable_create"),
    path("timetable/conflicts/", views.timetable_conflicts, name="timetable_conflicts"),
    
    # Student ID Cards
    path("id-cards/", views.id_card_list, name="id_card_list"),
    path("id-cards/create/", views.id_card_create, name="id_card_create"),
    path("id-cards/create-bulk/", views.id_card_create_bulk, name="id_card_create_bulk"),
    path("id-cards/<int:pk>/", views.id_card_view, name="id_card_view"),
    path("id-cards/<int:pk>/edit/", views.id_card_edit, name="id_card_edit"),
    path("id-cards/<int:pk>/delete/", views.id_card_delete, name="id_card_delete"),
    path("id-cards/<int:pk>/print/", views.id_card_print, name="id_card_print"),
    path("id-cards/<int:pk>/pdf/", views.id_card_pdf, name="id_card_pdf"),
    path("id-cards/export/zip/", views.id_card_export_zip, name="id_card_export_zip"),
    path("id-cards/export/pdf/", views.id_card_export_pdf, name="id_card_export_pdf"),
    
    # Staff ID Cards
    path("staff-id-cards/", views.staff_id_card_list, name="staff_id_card_list"),
    path("staff-id-cards/create/", views.staff_id_card_create, name="staff_id_card_create"),
    path("staff-id-cards/<int:pk>/edit/", views.staff_id_card_edit, name="staff_id_card_edit"),
    path("staff-id-cards/<int:pk>/delete/", views.staff_id_card_delete, name="staff_id_card_delete"),
    path("staff-id-cards/<int:pk>/print/", views.staff_id_card_print, name="staff_id_card_print"),
    path("staff-id-cards/<int:pk>/pdf/", views.staff_id_card_pdf, name="staff_id_card_pdf"),
    
    # Student Life (hub for students/parents)
    path("student-life/", views.student_life, name="student_life"),

    # Sports
    path("sports/", views.sport_list, name="sport_list"),
    path("sports/create/", views.sport_create, name="sport_create"),
    path("sports/<int:pk>/edit/", views.sport_edit, name="sport_edit"),
    path("sports/<int:pk>/", views.sport_detail, name="sport_detail"),
    path("sports/<int:pk>/delete/", views.sport_delete, name="sport_delete"),
    path("sports/<int:pk>/add-member/", views.sport_add_member, name="sport_add_member"),
    path("sports/<int:pk>/join/", views.sport_join_self, name="sport_join_self"),
    path("sports/<int:pk>/cancel-request/", views.sport_cancel_pending, name="sport_cancel_pending"),
    path(
        "sports/memberships/<int:pk>/approve/",
        views.sport_membership_approve,
        name="sport_membership_approve",
    ),
    path(
        "sports/memberships/<int:pk>/reject/",
        views.sport_membership_reject,
        name="sport_membership_reject",
    ),

    # Clubs
    path("clubs/", views.club_list, name="club_list"),
    path("clubs/create/", views.club_create, name="club_create"),
    path("clubs/<int:pk>/edit/", views.club_edit, name="club_edit"),
    path("clubs/<int:pk>/", views.club_detail, name="club_detail"),
    path("clubs/<int:pk>/delete/", views.club_delete, name="club_delete"),
    path("clubs/<int:pk>/add-member/", views.club_add_member, name="club_add_member"),
    path("clubs/<int:pk>/join/", views.club_join_self, name="club_join_self"),
    path("clubs/<int:pk>/cancel-request/", views.club_cancel_pending, name="club_cancel_pending"),
    path(
        "clubs/memberships/<int:pk>/approve/",
        views.club_membership_approve,
        name="club_membership_approve",
    ),
    path(
        "clubs/memberships/<int:pk>/reject/",
        views.club_membership_reject,
        name="club_membership_reject",
    ),

    # My Activities (Student View)
    path("my-activities/", views.my_activities, name="my_activities"),
    
    # Exam Halls
    path("exam-halls/", views.exam_hall_list, name="exam_hall_list"),
    path("exam-halls/create/", views.exam_hall_create, name="exam_hall_create"),
    path("exam-halls/<int:pk>/delete/", views.exam_hall_delete, name="exam_hall_delete"),
    
    # Seating Plans
    path("seating-plans/", views.seating_plan_list, name="seating_plan_list"),
    path("seating-plans/create/", views.seating_plan_create, name="seating_plan_create"),
    path("seating-plans/<int:pk>/", views.seating_plan_view, name="seating_plan_view"),
    
    # Health Records
    path("health-records/", views.health_record_list, name="health_record_list"),
    path("health-records/create/", views.health_record_create, name="health_record_create"),
    path("health-records/<int:pk>/edit/", views.health_record_edit, name="health_record_edit"),
    path("health-records/<int:pk>/delete/", views.health_record_delete, name="health_record_delete"),
    path("health-visits/", views.health_visit_list, name="health_visit_list"),
    path("health-visits/create/", views.health_visit_create, name="health_visit_create"),
    
    # Inventory Management
    path("inventory/categories/", views.inventory_category_list, name="inventory_category_list"),
    path("inventory/categories/create/", views.inventory_category_create, name="inventory_category_create"),
    path("inventory/categories/<int:pk>/edit/", views.inventory_category_edit, name="inventory_category_edit"),
    path("inventory/categories/<int:pk>/delete/", views.inventory_category_delete, name="inventory_category_delete"),
    path("inventory/items/", views.inventory_item_list, name="inventory_item_list"),
    path("inventory/items/create/", views.inventory_item_create, name="inventory_item_create"),
    path("inventory/items/<int:pk>/edit/", views.inventory_item_edit, name="inventory_item_edit"),
    path("inventory/items/<int:pk>/delete/", views.inventory_item_delete, name="inventory_item_delete"),
    path("inventory/transactions/", views.inventory_transaction_list, name="inventory_transaction_list"),
    path("inventory/transactions/create/", views.inventory_transaction_create, name="inventory_transaction_create"),
    
    # School Events
    path("events/", views.school_event_list, name="school_event_list"),
    path("events/create/", views.school_event_create, name="school_event_create"),
    path("events/<int:pk>/", views.school_event_detail, name="school_event_detail"),
    path("events/<int:pk>/edit/", views.school_event_edit, name="school_event_edit"),
    path("events/<int:pk>/delete/", views.school_event_delete, name="school_event_delete"),
    path("events/<int:pk>/rsvp/", views.school_event_rsvp, name="school_event_rsvp"),
    
    # Homework for Students & Parents
    path("homework/", views.homework_for_student, name="homework_for_student"),
    path("homework/<int:homework_id>/submit/", views.homework_submit, name="homework_submit"),
    
    # Assignment Submissions
    path("submissions/", views.assignment_submission_list, name="assignment_submission_list"),
    path("submissions/<int:pk>/grade/", views.assignment_submission_grade, name="assignment_submission_grade"),
    path("my-submissions/", views.my_submissions, name="my_submissions"),
    
    # Online Exams
    path("online-exams/", views.online_exam_list, name="online_exam_list"),
    path("online-exams/create/", views.online_exam_create, name="online_exam_create"),
    path("online-exams/results/", views.online_exam_results, name="online_exam_results"),
    path(
        "online-exams/essay-queue/",
        views.online_exam_essay_queue,
        name="online_exam_essay_queue",
    ),
    path("online-exams/results/<int:exam_id>/export/", views.online_exam_export_results, name="online_exam_export_results"),
    path("online-exams/<int:pk>/", views.online_exam_detail, name="online_exam_detail"),
    path("online-exams/<int:pk>/edit/", views.online_exam_edit, name="online_exam_edit"),
    path("online-exams/<int:pk>/delete/", views.online_exam_delete, name="online_exam_delete"),
    path("online-exams/<int:pk>/publish/", views.online_exam_publish, name="online_exam_publish"),
    path("online-exams/<int:pk>/add-question/", views.online_exam_add_question, name="online_exam_add_question"),
    path("online-exams/<int:pk>/take/", views.online_exam_take, name="online_exam_take"),
    path("online-exams/result/<int:pk>/", views.online_exam_result, name="online_exam_result"),
    path("online-exams/retake/<int:attempt_id>/", views.online_exam_allow_retake, name="online_exam_allow_retake"),
    path(
        "online-exams/attempt/<int:attempt_id>/delete/",
        views.online_exam_attempt_delete,
        name="online_exam_attempt_delete",
    ),
    path(
        "online-exams/attempt/<int:attempt_id>/grade/",
        views.online_exam_grade_attempt,
        name="online_exam_grade_attempt",
    ),
    
    # PT Meetings
    path("pt-meetings/", views.pt_meeting_list, name="pt_meeting_list"),
    path("pt-meetings/create/", views.pt_meeting_create, name="pt_meeting_create"),
    path("pt-meetings/<int:pk>/", views.pt_meeting_detail, name="pt_meeting_detail"),
    path("pt-meetings/<int:pk>/edit/", views.pt_meeting_edit, name="pt_meeting_edit"),
    path("pt-meetings/<int:pk>/delete/", views.pt_meeting_delete, name="pt_meeting_delete"),
    path("pt-meetings/<int:pk>/book/", views.pt_meeting_book, name="pt_meeting_book"),
    
    # NEW: Advanced Operations Features
    # Auto Timetable Generator
    path("auto-timetable/", advanced_views.auto_timetable_page, name="auto_timetable_page"),
    path("auto-timetable/generate/", advanced_views.generate_timetable, name="generate_timetable"),
    
    # Auto Seating Plan
    path("auto-seating-plan/", advanced_views.auto_seating_plan_page, name="auto_seating_plan_page"),
    path("auto-seating-plan/generate/", advanced_views.generate_seating_plan, name="generate_seating_plan"),
    
    # Behavior Tracker
    path("behavior-tracker/", advanced_views.behavior_tracker_page, name="behavior_tracker_page"),
    path("behavior-tracker/record/", advanced_views.record_behavior, name="record_behavior"),
    path("behavior-tracker/student/<int:student_id>/", advanced_views.student_behavior_history, name="student_behavior_history"),
    
    # School-wide performance rankings (attendance + results blend)
    path("school-rankings/", advanced_views.class_rankings_page, name="school_rankings"),

    # Financial Reports
    path("financial-reports/", advanced_views.financial_reports_page, name="financial_reports_page"),
    path("financial-reports/data/", advanced_views.get_financial_data, name="financial_reports_data"),
    path("financial-reports/budget-vs-actual/", advanced_views.budget_vs_actual, name="budget_vs_actual"),
    path("financial-reports/income-statement/", advanced_views.income_statement, name="income_statement"),
    path("financial-reports/expense-breakdown/", advanced_views.expense_breakdown, name="expense_breakdown"),
]