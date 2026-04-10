"""Teaching scope (attendance + results), management vs teacher rules, and light URL smoke checks."""

from datetime import time

from django.test import Client, TestCase
from django.urls import reverse

from academics.models import ExamType, Result, Subject, Term, Timetable
from accounts.models import User
from schools.models import School
from students.models import SchoolClass, Student


class TeachingScopeAndSmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Scope Test School", subdomain="scope-test-sch-x9")
        cls.subj_math = Subject.objects.create(school=cls.school, name="Mathematics")
        cls.subj_eng = Subject.objects.create(school=cls.school, name="English")
        cls.term = Term.objects.create(school=cls.school, name="Term 1", is_current=True)
        cls.exam = ExamType.objects.create(school=cls.school, name="Test Exam")

        cls.class_a = SchoolClass.objects.create(school=cls.school, name="Form 1A")
        cls.class_b = SchoolClass.objects.create(school=cls.school, name="Form 1B")

        cls.admin = User.objects.create_user(
            username="scope_admin", password="pass12345", school=cls.school, role="school_admin"
        )
        cls.hod = User.objects.create_user(
            username="scope_hod", password="pass12345", school=cls.school, role="hod"
        )
        cls.teacher_homeroom = User.objects.create_user(
            username="scope_th", password="pass12345", school=cls.school, role="teacher"
        )
        cls.class_a.class_teacher = cls.teacher_homeroom
        cls.class_a.save(update_fields=["class_teacher"])

        cls.teacher_tt = User.objects.create_user(
            username="scope_tt", password="pass12345", school=cls.school, role="teacher"
        )
        Timetable.objects.create(
            school=cls.school,
            class_name="Form 1B",
            subject=cls.subj_math,
            teacher=cls.teacher_tt,
            day_of_week="Monday",
            start_time=time(8, 0),
            end_time=time(9, 0),
        )

        su_math = User.objects.create_user(
            username="stu_math", password="pass12345", school=cls.school, role="student"
        )
        su_eng = User.objects.create_user(
            username="stu_eng", password="pass12345", school=cls.school, role="student"
        )
        cls.student_math = Student.objects.create(
            school=cls.school,
            user=su_math,
            admission_number="S001",
            class_name="Form 1B",
        )
        cls.student_eng = Student.objects.create(
            school=cls.school,
            user=su_eng,
            admission_number="S002",
            class_name="Form 1A",
        )
        Result.objects.create(
            student=cls.student_math,
            subject=cls.subj_math,
            exam_type=cls.exam,
            term=cls.term,
            score=80,
            total_score=100,
        )
        Result.objects.create(
            student=cls.student_eng,
            subject=cls.subj_eng,
            exam_type=cls.exam,
            term=cls.term,
            score=70,
            total_score=100,
        )

    def setUp(self):
        self.client = Client()

    def test_hod_attendance_sees_all_classes(self):
        self.client.login(username="scope_hod", password="pass12345")
        r = self.client.get(reverse("operations:attendance_mark"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Form 1A")
        self.assertContains(r, "Form 1B")

    def test_teacher_homeroom_sees_only_homeroom_class(self):
        self.client.login(username="scope_th", password="pass12345")
        r = self.client.get(reverse("operations:attendance_mark"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Form 1A")
        self.assertNotContains(r, ">Form 1B</option>")

    def test_teacher_timetable_sees_only_timetable_class(self):
        self.client.login(username="scope_tt", password="pass12345")
        r = self.client.get(reverse("operations:attendance_mark"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Form 1B")
        self.assertNotContains(r, ">Form 1A</option>")

    def test_results_management_teacher_scoped_to_subjects(self):
        self.client.login(username="scope_tt", password="pass12345")
        r = self.client.get(reverse("academics:results_management"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "stu_math")
        self.assertNotContains(r, "stu_eng")
        self.assertContains(r, "your subjects")

    def test_results_management_admin_sees_all_recent(self):
        self.client.login(username="scope_admin", password="pass12345")
        r = self.client.get(reverse("academics:results_management"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "stu_math")
        self.assertContains(r, "stu_eng")
        self.assertNotContains(r, "your subjects")

    def test_superuser_send_message_requires_privilege(self):
        plain = User.objects.create_user(username="plain_u", password="pass12345", school=self.school, role="teacher")
        self.client.login(username="plain_u", password="pass12345")
        r = self.client.get(reverse("messaging:superuser_send_message"))
        self.assertEqual(r.status_code, 302)

    def test_parent_portal_authenticated_ok(self):
        parent = User.objects.create_user(
            username="scope_parent", password="pass12345", school=self.school, role="parent"
        )
        self.client.login(username="scope_parent", password="pass12345")
        r = self.client.get(reverse("portal"))
        self.assertIn(r.status_code, (200, 302))

    def test_student_results_list_authenticated_ok(self):
        self.client.login(username="stu_math", password="pass12345")
        r = self.client.get(reverse("students:results_list"))
        self.assertEqual(r.status_code, 200)
