# Generated manually — extend SchoolFeature.key choices

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0008_alter_school_options_alter_schoolfeature_options"),
    ]

    operations = [
        migrations.AlterField(
            model_name="schoolfeature",
            name="key",
            field=models.CharField(
                choices=[
                    ("hostel", "Hostel"),
                    ("library", "Library"),
                    ("inventory", "Inventory"),
                    ("messaging", "Messaging"),
                    ("ai_assistant", "AI Assistant"),
                    ("finance_admin", "Finance (admin tools)"),
                    ("exams", "Exams & Assessments"),
                    ("homework", "Homework"),
                    ("quiz", "Online Quizzes"),
                    ("results", "Results & Report Cards"),
                    ("timetable", "Timetable"),
                    ("performance_analytics", "Performance Analytics"),
                    ("admission", "Admissions"),
                    ("student_enrollment", "Student Enrollment"),
                    ("attendance", "Student Attendance"),
                    ("teacher_attendance", "Teacher Attendance"),
                    ("bus_transport", "Bus Transport"),
                    ("canteen", "Canteen"),
                    ("textbooks", "Textbooks"),
                    ("certificates", "Certificates"),
                    ("id_cards", "ID Cards"),
                    ("health_records", "Health Records"),
                    ("discipline", "Discipline & Behavior"),
                    ("academic_calendar", "Academic Calendar"),
                    ("school_events", "School Events"),
                    ("sports", "Sports"),
                    ("clubs", "Clubs & Activities"),
                    ("pt_meetings", "Parent-Teacher Meetings"),
                    ("alumni", "Alumni"),
                    ("documents", "Documents"),
                    ("announcements", "Announcements"),
                    ("online_exams", "Online Exams"),
                    ("fee_management", "Fee Management"),
                    ("online_payments", "Online Payments"),
                    ("expenses", "Expenses"),
                    ("budgets", "Budgets"),
                    ("staff_management", "Staff Management"),
                    ("leave_management", "Leave Management"),
                ],
                max_length=40,
            ),
        ),
    ]
