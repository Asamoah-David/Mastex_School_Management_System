"""Timetable create: teacher FK must belong to the same school."""

import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from academics.models import Subject, Timetable
from schools.models import School

User = get_user_model()


class TimetableCreateTeacherScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school_a = School.objects.create(name="TT A", subdomain=f"tta-{uuid.uuid4().hex[:8]}")
        cls.school_b = School.objects.create(name="TT B", subdomain=f"ttb-{uuid.uuid4().hex[:8]}")
        cls.admin_a = User.objects.create_user(
            username="tt_admin_a", password="pw12345", school=cls.school_a, role="school_admin"
        )
        cls.teacher_b = User.objects.create_user(
            username="tt_teacher_b", password="pw12345", school=cls.school_b, role="teacher"
        )
        cls.subj_a = Subject.objects.create(school=cls.school_a, name="Math")

    def setUp(self):
        self.client = Client()

    def test_cannot_assign_teacher_from_other_school(self):
        self.client.login(username="tt_admin_a", password="pw12345")
        before = Timetable.objects.filter(school=self.school_a).count()
        url = reverse("academics:timetable_create")
        r = self.client.post(
            url,
            {
                "class_name": "X1",
                "subject": str(self.subj_a.pk),
                "teacher": str(self.teacher_b.pk),
                "venue": "Lab 1",
                "day": "Monday",
                "start_time": "09:00",
                "end_time": "10:00",
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Timetable.objects.filter(school=self.school_a).count(), before)
