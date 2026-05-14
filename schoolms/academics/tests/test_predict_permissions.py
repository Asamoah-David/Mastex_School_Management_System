"""Access control for predict_student_performance JSON (academics audit)."""

import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from academics.models import ExamType, Result, Subject, Term
from schools.models import School
from students.models import Student

User = get_user_model()


class PredictStudentPerformancePermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Pred School", subdomain=f"pred-{uuid.uuid4().hex[:8]}")
        cls.term = Term.objects.create(school=cls.school, name="T1")
        cls.subject = Subject.objects.create(school=cls.school, name="Math")
        cls.exam_mid = ExamType.objects.create(school=cls.school, name="Mid")
        cls.exam_end = ExamType.objects.create(school=cls.school, name="End")

        cls.teacher = User.objects.create_user(
            username="pred_teacher", password="pw12345", school=cls.school, role="teacher"
        )
        cls.peer = User.objects.create_user(
            username="pred_peer", password="pw12345", school=cls.school, role="student"
        )
        cls.owner = User.objects.create_user(
            username="pred_owner", password="pw12345", school=cls.school, role="student"
        )

        cls.student_peer = Student.objects.create(
            school=cls.school,
            user=cls.peer,
            admission_number="P-PEER",
            class_name="1A",
            status="active",
        )
        cls.student_owner = Student.objects.create(
            school=cls.school,
            user=cls.owner,
            admission_number="P-OWN",
            class_name="1A",
            status="active",
        )

        for st, pairs in (
            (cls.student_peer, ((cls.exam_mid, 55.0), (cls.exam_end, 60.0))),
            (cls.student_owner, ((cls.exam_mid, 70.0), (cls.exam_end, 72.0))),
        ):
            for exam, sc in pairs:
                Result.objects.create(
                    school=cls.school,
                    student=st,
                    subject=cls.subject,
                    exam_type=exam,
                    term=cls.term,
                    score=sc,
                    total_score=100,
                    created_by=cls.teacher,
                    is_published=True,
                )

    def setUp(self):
        self.client = Client()

    def test_peer_student_cannot_fetch_prediction_for_classmate(self):
        self.client.login(username="pred_peer", password="pw12345")
        url = reverse("academics:predict_student_performance", kwargs={"student_id": self.student_owner.pk})
        r = self.client.get(url)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json().get("error"), "Forbidden")

    def test_student_can_fetch_own_prediction(self):
        self.client.login(username="pred_owner", password="pw12345")
        url = reverse("academics:predict_student_performance", kwargs={"student_id": self.student_owner.pk})
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("predicted_score", data)

    def test_teacher_can_fetch_prediction_for_student(self):
        self.client.login(username="pred_teacher", password="pw12345")
        url = reverse("academics:predict_student_performance", kwargs={"student_id": self.student_peer.pk})
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertIn("predicted_score", r.json())
