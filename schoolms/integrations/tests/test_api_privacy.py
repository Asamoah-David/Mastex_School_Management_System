"""API tenant and privacy rules for published results and transcripts."""

from django.test import Client, TestCase
from django.urls import reverse

from academics.models import ExamType, Result, Subject, Term
from accounts.models import User
from schools.models import School
from students.models import Student


class ApiPublishedResultsPrivacyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="API Privacy School", subdomain="api-priv-sch-01")
        cls.subject = Subject.objects.create(school=cls.school, name="Math")
        cls.term = Term.objects.create(school=cls.school, name="T1", is_current=True)
        cls.exam = ExamType.objects.create(school=cls.school, name="Midterm")

        cls.teacher = User.objects.create_user(
            username="api_priv_teacher", password="pass12345", school=cls.school, role="teacher"
        )
        cls.librarian = User.objects.create_user(
            username="api_priv_lib", password="pass12345", school=cls.school, role="librarian"
        )
        cls.parent = User.objects.create_user(
            username="api_priv_parent", password="pass12345", school=cls.school, role="parent"
        )
        su = User.objects.create_user(
            username="api_priv_stu", password="pass12345", school=cls.school, role="student"
        )
        cls.student = Student.objects.create(
            school=cls.school,
            user=su,
            admission_number="AP01",
            class_name="Form 1",
            parent=cls.parent,
        )
        other_su = User.objects.create_user(
            username="api_priv_stu2", password="pass12345", school=cls.school, role="student"
        )
        cls.other_student = Student.objects.create(
            school=cls.school,
            user=other_su,
            admission_number="AP02",
            class_name="Form 2",
        )
        Result.objects.create(
            school=cls.school,
            student=cls.student,
            subject=cls.subject,
            exam_type=cls.exam,
            term=cls.term,
            score=80,
            total_score=100,
            is_published=True,
        )
        Result.objects.create(
            school=cls.school,
            student=cls.other_student,
            subject=cls.subject,
            exam_type=cls.exam,
            term=cls.term,
            score=50,
            total_score=100,
            is_published=True,
        )

    def setUp(self):
        self.client = Client()

    def test_librarian_cannot_list_results(self):
        self.client.login(username="api_priv_lib", password="pass12345")
        r = self.client.get(reverse("integrations:v1_results"))
        self.assertEqual(r.status_code, 403)

    def test_teacher_sees_all_published_in_school(self):
        self.client.login(username="api_priv_teacher", password="pass12345")
        r = self.client.get(reverse("integrations:v1_results"))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["count"], 2)

    def test_parent_sees_only_linked_child_results(self):
        self.client.login(username="api_priv_parent", password="pass12345")
        r = self.client.get(reverse("integrations:v1_results"))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["student_id"], self.student.pk)

    def test_student_sees_only_own_results(self):
        self.client.login(username="api_priv_stu", password="pass12345")
        r = self.client.get(reverse("integrations:v1_results"))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["student_id"], self.student.pk)

    def test_transcript_forbidden_for_other_student(self):
        self.client.login(username="api_priv_stu", password="pass12345")
        url = reverse(
            "integrations:v1_student_transcripts",
            kwargs={"student_id": self.other_student.pk},
        )
        r = self.client.get(url)
        self.assertEqual(r.status_code, 403)
