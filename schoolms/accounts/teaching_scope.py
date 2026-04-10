"""Which classes and subjects a staff member is tied to (homeroom, timetable, assignments).

Used for attendance class pickers, results activity widgets, and teacher dashboards.
"""

from __future__ import annotations

from django.db.models import QuerySet

from schools.models import School


def teacher_attendance_classes_qs(school: School, user) -> QuerySet:
    """
    SchoolClass rows the user may mark *student* attendance for:
    homeroom (class teacher) ∪ classes on their weekly timetable.
    """
    from students.models import SchoolClass
    from academics.models import Timetable

    homeroom = SchoolClass.objects.filter(school=school, class_teacher=user)
    timetable_names = list(
        Timetable.objects.filter(school=school, teacher=user)
        .values_list("class_name", flat=True)
        .distinct()
    )
    if not timetable_names:
        timetable_classes = SchoolClass.objects.none()
    else:
        timetable_classes = SchoolClass.objects.filter(school=school, name__in=timetable_names)
    return (homeroom | timetable_classes).distinct().order_by("name")


def teacher_result_subject_ids(school: School, user) -> set[int]:
    """
    Subject IDs for scoping academic results to this teacher's workload
    (assigned subjects, timetable, homework created, quizzes created).
    """
    from academics.models import Timetable, Homework, Quiz

    assigned_ids = list(user.assigned_subjects.filter(school=school).values_list("id", flat=True))
    timetable_subject_ids = list(
        Timetable.objects.filter(school=school, teacher=user)
        .values_list("subject_id", flat=True)
        .distinct()
    )
    homework_subject_ids = list(
        Homework.objects.filter(school=school, created_by=user)
        .values_list("subject_id", flat=True)
        .distinct()
    )
    quiz_subject_ids = list(
        Quiz.objects.filter(school=school, created_by=user)
        .values_list("subject_id", flat=True)
        .distinct()
    )
    return (
        set(assigned_ids)
        | set(timetable_subject_ids)
        | set(homework_subject_ids)
        | set(quiz_subject_ids)
    )
