import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from academics.models import ExamType, Result, ScoreChangeLog, Subject, Term
from schools.models import School
from students.models import Student


class ResultWorkflowLockTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.school = School.objects.create(name="T1", subdomain=f"t1-{uuid.uuid4().hex[:8]}")
        self.user = User.objects.create_user(username="u1", password="x")
        self.user.school = self.school
        self.user.save(update_fields=["school"])
        self.term = Term.objects.create(school=self.school, name="Term 1")
        self.subject = Subject.objects.create(school=self.school, name="Math")
        self.exam = ExamType.objects.create(school=self.school, name="Exam")
        self.student = Student.objects.create(
            school=self.school,
            user=User.objects.create_user(username="stu1", password="x"),
            admission_number="A1",
            class_name="P1",
        )

    def test_locked_blocks_score_change(self):
        r = Result.objects.create(
            school=self.school,
            student=self.student,
            subject=self.subject,
            exam_type=self.exam,
            term=self.term,
            score=40,
            total_score=100,
            created_by=self.user,
            workflow_status=Result.WORKFLOW_LOCKED,
        )
        r.score = 50
        with self.assertRaises(ValidationError):
            r.full_clean()

    def test_locked_allows_unlock_change(self):
        r = Result.objects.create(
            school=self.school,
            student=self.student,
            subject=self.subject,
            exam_type=self.exam,
            term=self.term,
            score=40,
            total_score=100,
            created_by=self.user,
            workflow_status=Result.WORKFLOW_LOCKED,
        )
        r.workflow_status = Result.WORKFLOW_REVIEWED
        r.full_clean()

    def test_queryset_update_logs_sensitive_changes(self):
        r = Result.objects.create(
            school=self.school,
            student=self.student,
            subject=self.subject,
            exam_type=self.exam,
            term=self.term,
            score=40,
            total_score=100,
            created_by=self.user,
            remarks="old",
        )
        Result.objects.filter(pk=r.pk).update(score=55, remarks="new")
        logs = ScoreChangeLog.objects.filter(target_model="academics.result", target_id=r.pk)
        self.assertTrue(logs.filter(field_name="score", old_value="40.0", new_value="55").exists())
        self.assertTrue(logs.filter(field_name="remarks", old_value="old", new_value="new").exists())

    def test_queryset_update_blocks_locked_score_change(self):
        r = Result.objects.create(
            school=self.school,
            student=self.student,
            subject=self.subject,
            exam_type=self.exam,
            term=self.term,
            score=40,
            total_score=100,
            created_by=self.user,
            workflow_status=Result.WORKFLOW_LOCKED,
        )
        with self.assertRaises(ValidationError):
            Result.objects.filter(pk=r.pk).update(score=60)


class ResultWorkflowBulkActionViewTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.school = School.objects.create(name="T2", subdomain=f"t2-{uuid.uuid4().hex[:8]}")
        self.exam_officer = User.objects.create_user(
            username="exam_officer_1", password="x", role="exam_officer", school=self.school
        )
        self.teacher = User.objects.create_user(
            username="teacher_1", password="x", role="teacher", school=self.school
        )
        self.term = Term.objects.create(school=self.school, name="Term 1")
        self.subject = Subject.objects.create(school=self.school, name="English")
        self.exam = ExamType.objects.create(school=self.school, name="Midterm")
        self.student = Student.objects.create(
            school=self.school,
            user=User.objects.create_user(username="stu2", password="x", school=self.school),
            admission_number="A2",
            class_name="P2",
        )
        self.result = Result.objects.create(
            school=self.school,
            student=self.student,
            subject=self.subject,
            exam_type=self.exam,
            term=self.term,
            score=65,
            total_score=100,
            created_by=self.teacher,
            workflow_status=Result.WORKFLOW_DRAFT,
        )

    def test_exam_officer_can_approve_publish_and_lock(self):
        self.client.force_login(self.exam_officer)
        url = reverse("academics:result_list")
        self.client.post(url, {"action": "approve"})
        self.result.refresh_from_db()
        self.assertEqual(self.result.workflow_status, Result.WORKFLOW_APPROVED)
        self.client.post(url, {"action": "publish"})
        self.result.refresh_from_db()
        self.assertEqual(self.result.workflow_status, Result.WORKFLOW_PUBLISHED)
        self.assertTrue(self.result.is_published)
        self.client.post(url, {"action": "lock"})
        self.result.refresh_from_db()
        self.assertEqual(self.result.workflow_status, Result.WORKFLOW_LOCKED)

    def test_teacher_cannot_publish(self):
        self.client.force_login(self.teacher)
        url = reverse("academics:result_list")
        self.client.post(url, {"action": "publish"})
        self.result.refresh_from_db()
        self.assertEqual(self.result.workflow_status, Result.WORKFLOW_DRAFT)
