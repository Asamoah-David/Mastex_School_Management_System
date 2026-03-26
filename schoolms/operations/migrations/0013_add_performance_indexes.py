"""
Migration to add database indexes for performance optimization.
This improves query speed on frequently accessed fields.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0012_staffidcard'),
    ]

    operations = [
        # TeacherAttendance indexes
        migrations.AddIndex(
            model_name='teacherattendance',
            index=models.Index(fields=['school', 'date'], name='ops_teacheratte_school_date_idx'),
        ),
        migrations.AddIndex(
            model_name='teacherattendance',
            index=models.Index(fields=['teacher', 'date'], name='ops_teacheratte_teacher_date_idx'),
        ),

        # AcademicCalendar indexes
        migrations.AddIndex(
            model_name='academiccalendar',
            index=models.Index(fields=['school', 'start_date'], name='ops_academicca_school_start_idx'),
        ),

        # StudentAttendance indexes
        migrations.AddIndex(
            model_name='studentattendance',
            index=models.Index(fields=['school', 'date'], name='ops_studentatte_school_date_idx'),
        ),
        migrations.AddIndex(
            model_name='studentattendance',
            index=models.Index(fields=['student', 'date'], name='ops_studentatte_student_date_idx'),
        ),

        # CanteenPayment indexes
        migrations.AddIndex(
            model_name='canteenpayment',
            index=models.Index(fields=['school', 'payment_date'], name='ops_canteenpay_school_date_idx'),
        ),

        # BusPayment indexes
        migrations.AddIndex(
            model_name='buspayment',
            index=models.Index(fields=['school', 'paid'], name='ops_buspayment_school_paid_idx'),
        ),

        # LibraryIssue indexes
        migrations.AddIndex(
            model_name='libraryissue',
            index=models.Index(fields=['school', 'status'], name='ops_libraryissue_school_status_idx'),
        ),
        migrations.AddIndex(
            model_name='libraryissue',
            index=models.Index(fields=['student', 'status'], name='ops_libraryissue_student_status_idx'),
        ),

        # HostelFee indexes
        migrations.AddIndex(
            model_name='hostelfee',
            index=models.Index(fields=['school', 'paid'], name='ops_hostelfee_school_paid_idx'),
        ),

        # StaffLeave indexes
        migrations.AddIndex(
            model_name='staffleave',
            index=models.Index(fields=['school', 'status'], name='ops_staffleave_school_status_idx'),
        ),
        migrations.AddIndex(
            model_name='staffleave',
            index=models.Index(fields=['school', 'start_date'], name='ops_staffleave_school_start_idx'),
        ),

        # ActivityLog indexes
        migrations.AddIndex(
            model_name='activitylog',
            index=models.Index(fields=['user', 'created_at'], name='ops_activitylog_user_created_idx'),
        ),

        # HealthVisit indexes
        migrations.AddIndex(
            model_name='healthvisit',
            index=models.Index(fields=['school', 'visit_date'], name='ops_healthvisit_school_date_idx'),
        ),

        # Expense indexes
        migrations.AddIndex(
            model_name='expense',
            index=models.Index(fields=['school', 'expense_date'], name='ops_expense_school_date_idx'),
        ),

        # DisciplineIncident indexes
        migrations.AddIndex(
            model_name='disciplineincident',
            index=models.Index(fields=['school', 'incident_date'], name='ops_discipline_school_date_idx'),
        ),
        migrations.AddIndex(
            model_name='disciplineincident',
            index=models.Index(fields=['student', 'incident_date'], name='ops_discipline_student_date_idx'),
        ),

        # BehaviorPoint indexes
        migrations.AddIndex(
            model_name='behaviorpoint',
            index=models.Index(fields=['school', 'awarded_at'], name='ops_behaviorpo_school_awarded_idx'),
        ),

        # AssignmentSubmission indexes
        migrations.AddIndex(
            model_name='assignmentsubmission',
            index=models.Index(fields=['homework', 'status'], name='ops_assignments_homework_status_idx'),
        ),

        # OnlineExam indexes
        migrations.AddIndex(
            model_name='onlineexam',
            index=models.Index(fields=['school', 'status'], name='ops_onlineexam_school_status_idx'),
        ),

        # ExamAttempt indexes
        migrations.AddIndex(
            model_name='examattempt',
            index=models.Index(fields=['exam', 'student'], name='ops_examattempt_exam_student_idx'),
        ),

        # TimetableSlot indexes
        migrations.AddIndex(
            model_name='timetableslot',
            index=models.Index(fields=['school', 'class_name', 'day'], name='ops_timetableslo_school_class_idx'),
        ),
    ]
