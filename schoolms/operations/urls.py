from django.urls import path
from . import views

app_name = "operations"

urlpatterns = [
    # Student Attendance
    path("attendance/", views.attendance_list, name="attendance_list"),
    path("attendance/mark/", views.attendance_mark, name="attendance_mark"),
    path("attendance/edit/<int:pk>/", views.attendance_edit, name="attendance_edit"),
    path("attendance/delete/<int:pk>/", views.attendance_delete, name="attendance_delete"),
    
    # Teacher Attendance
    path("teacher-attendance/", views.teacher_attendance_list, name="teacher_attendance_list"),
    path("teacher-attendance/mark/", views.teacher_attendance_mark, name="teacher_attendance_mark"),
    
    # Academic Calendar
    path("calendar/", views.calendar_list, name="calendar"),
    path("calendar/create/", views.calendar_create, name="calendar_create"),
    path("calendar/delete/<int:pk>/", views.calendar_delete, name="calendar_delete"),
    
    # Canteen
    path("canteen/", views.canteen_list, name="canteen_list"),
    path("canteen/create/", views.canteen_create, name="canteen_create"),
    path("canteen/payments/", views.canteen_payments, name="canteen_payments"),
    path("canteen/delete/<int:pk>/", views.canteen_item_delete, name="canteen_item_delete"),
    
    # Bus
    path("bus/", views.bus_list, name="bus_list"),
    path("bus/create/", views.bus_create, name="bus_create"),
    path("bus/payments/", views.bus_payments, name="bus_payments"),
    path("bus/delete/<int:pk>/", views.bus_route_delete, name="bus_route_delete"),
    
    # Textbooks
    path("textbooks/", views.textbook_list, name="textbook_list"),
    path("textbooks/create/", views.textbook_create, name="textbook_create"),
    path("textbooks/sales/", views.textbook_sales, name="textbook_sales"),
    path("textbooks/delete/<int:pk>/", views.textbook_delete, name="textbook_delete"),

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
    path("hostels/assignments/", views.hostel_assignments, name="hostel_assignments"),
    path("hostels/assignments/create/", views.hostel_assignment_create, name="hostel_assignment_create"),
    path("hostels/assignments/<int:pk>/end/", views.hostel_assignment_end, name="hostel_assignment_end"),
    path("hostels/fees/", views.hostel_fees, name="hostel_fees"),
    path("hostels/fees/create/", views.hostel_fee_create, name="hostel_fee_create"),
    path("hostels/fees/<int:pk>/mark-paid/", views.hostel_fee_mark_paid, name="hostel_fee_mark_paid"),
    path("hostels/my/", views.hostel_my, name="hostel_my"),
    
    # Admission Applications
    path("admission/apply/", views.admission_apply, name="admission_apply"),
    path("admission/list/", views.admission_list, name="admission_list"),
    path("admission/<int:pk>/", views.admission_detail, name="admission_detail"),
    path("admission/<int:pk>/approve/", views.admission_approve, name="admission_approve"),
    path("admission/<int:pk>/reject/", views.admission_reject, name="admission_reject"),
    
    # Certificates
    path("certificates/", views.certificate_list, name="certificate_list"),
    path("certificates/create/", views.certificate_create, name="certificate_create"),
    path("certificates/<int:pk>/", views.certificate_view, name="certificate_view"),
    path("certificates/<int:pk>/delete/", views.certificate_delete, name="certificate_delete"),
    
    # Expense Tracking
    path("expenses/", views.expense_list, name="expense_list"),
    path("expenses/create/", views.expense_create, name="expense_create"),
    path("expenses/<int:pk>/", views.expense_detail, name="expense_detail"),
    
    # Budget
    path("budgets/", views.budget_list, name="budget_list"),
    path("budgets/create/", views.budget_create, name="budget_create"),
    
    # Expense Categories
    path("expense-categories/", views.expense_category_list, name="expense_category_list"),
    path("expense-categories/create/", views.expense_category_create, name="expense_category_create"),
    
    # Discipline
    path("discipline/", views.discipline_list, name="discipline_list"),
    path("discipline/create/", views.discipline_create, name="discipline_create"),
    path("discipline/<int:pk>/", views.discipline_detail, name="discipline_detail"),
    
    # Behavior Points
    path("behavior-points/", views.behavior_points_list, name="behavior_points_list"),
    path("behavior-points/create/", views.behavior_points_create, name="behavior_points_create"),
    
    # Documents
    path("documents/", views.document_list, name="document_list"),
    path("documents/upload/", views.document_upload, name="document_upload"),
    
    # Alumni
    path("alumni/", views.alumni_list, name="alumni_list"),
    path("alumni/create/", views.alumni_create, name="alumni_create"),
    path("alumni/<int:pk>/", views.alumni_detail, name="alumni_detail"),
    path("alumni/events/", views.alumni_event_list, name="alumni_event_list"),
    
    # Timetable
    path("timetable/", views.timetable_view, name="timetable_view"),
    path("timetable/create/", views.timetable_create, name="timetable_create"),
    path("timetable/conflicts/", views.timetable_conflicts, name="timetable_conflicts"),
    
    # Student ID Cards
    path("id-cards/", views.id_card_list, name="id_card_list"),
    path("id-cards/create/", views.id_card_create, name="id_card_create"),
    path("id-cards/<int:pk>/", views.id_card_view, name="id_card_view"),
    path("id-cards/<int:pk>/print/", views.id_card_print, name="id_card_print"),
    
    # Sports
    path("sports/", views.sport_list, name="sport_list"),
    path("sports/create/", views.sport_create, name="sport_create"),
    path("sports/<int:pk>/", views.sport_detail, name="sport_detail"),
    path("sports/<int:pk>/add-member/", views.sport_add_member, name="sport_add_member"),
    
    # Clubs
    path("clubs/", views.club_list, name="club_list"),
    path("clubs/create/", views.club_create, name="club_create"),
    path("clubs/<int:pk>/", views.club_detail, name="club_detail"),
    path("clubs/<int:pk>/add-member/", views.club_add_member, name="club_add_member"),
    
    # My Activities (Student View)
    path("my-activities/", views.my_activities, name="my_activities"),
    
    # Exam Halls
    path("exam-halls/", views.exam_hall_list, name="exam_hall_list"),
    path("exam-halls/create/", views.exam_hall_create, name="exam_hall_create"),
    
    # Seating Plans
    path("seating-plans/", views.seating_plan_list, name="seating_plan_list"),
    path("seating-plans/create/", views.seating_plan_create, name="seating_plan_create"),
    path("seating-plans/<int:pk>/", views.seating_plan_view, name="seating_plan_view"),
    
    # PT Meetings
    path("pt-meetings/", views.pt_meeting_list, name="pt_meeting_list"),
    path("pt-meetings/create/", views.pt_meeting_create, name="pt_meeting_create"),
    path("pt-meetings/<int:pk>/", views.pt_meeting_detail, name="pt_meeting_detail"),
    path("pt-meetings/<int:pk>/book/", views.pt_meeting_book, name="pt_meeting_book"),
]
