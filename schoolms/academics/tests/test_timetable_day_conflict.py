"""Timetable conflict helpers treat day names case-insensitively."""

import uuid
from datetime import time

from django.test import TestCase

from academics.models import Subject, Timetable
from academics.views import _timetable_class_slot_conflicts
from accounts.models import User
from schools.models import School
from students.models import Student


class TimetableDayIExactConflictTests(TestCase):
    def test_cross_casing_day_still_conflicts(self):
        school = School.objects.create(name="Day Sch", subdomain=f"day-{uuid.uuid4().hex[:8]}")
        u = User.objects.create_user(username="day_u", password="x")
        u.school = school
        u.save(update_fields=["school"])
        Student.objects.create(
            school=school, user=u, admission_number="D1", class_name="C1",
        )
        sub = Subject.objects.create(school=school, name="S")
        Timetable.objects.create(
            school=school,
            class_name="C1",
            subject=sub,
            day_of_week="Monday",
            start_time=time(9, 0),
            end_time=time(10, 0),
            venue="A1",
        )
        hits = _timetable_class_slot_conflicts(
            school, "C1", "monday", time(9, 15), time(9, 45)
        )
        self.assertEqual(len(hits), 1)
