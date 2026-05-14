"""StudentResultSummary refresh via AssessmentScore / ExamScore signals."""
import uuid
from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from academics.models import (
    AssessmentScore,
    AssessmentType,
    ExamScore,
    ExamType,
    Result,
    StudentResultSummary,
    Subject,
    Term,
)
from academics.services import GradingService
from schools.models import School
from students.models import Student


class ScoreSummarySignalTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.school = School.objects.create(name="Sig", subdomain=f"sig-{uuid.uuid4().hex[:8]}")
        self.term = Term.objects.create(school=self.school, name="T1")
        self.subject = Subject.objects.create(school=self.school, name="Math")
        self.assessment_type = AssessmentType.objects.create(
            school=self.school, name="Quiz 1", is_active=True
        )
        self.exam_type = ExamType.objects.create(school=self.school, name="End Term")
        self.student = Student.objects.create(
            school=self.school,
            user=User.objects.create_user(username=f"stu-{uuid.uuid4().hex[:8]}", password="x"),
            admission_number="S1",
            class_name="P1",
        )

    def test_assessment_save_creates_summary_after_commit(self):
        with self.captureOnCommitCallbacks(execute=True):
            AssessmentScore.objects.create(
                student=self.student,
                subject=self.subject,
                term=self.term,
                assessment_type=self.assessment_type,
                score=80.0,
                date=date.today(),
            )
        summary = StudentResultSummary.objects.filter(
            student=self.student, subject=self.subject, term=self.term
        ).first()
        self.assertIsNotNone(summary)
        self.assertEqual(summary.ca_score, 80.0)

    def test_exam_save_updates_summary(self):
        with self.captureOnCommitCallbacks(execute=True):
            ExamScore.objects.create(
                student=self.student,
                subject=self.subject,
                term=self.term,
                exam_type=self.exam_type,
                score=90.0,
                date=date.today(),
            )
        summary = StudentResultSummary.objects.get(
            student=self.student, subject=self.subject, term=self.term
        )
        self.assertEqual(summary.exam_score, 90.0)

    def test_delete_last_assessment_removes_summary(self):
        with self.captureOnCommitCallbacks(execute=True):
            a = AssessmentScore.objects.create(
                student=self.student,
                subject=self.subject,
                term=self.term,
                assessment_type=self.assessment_type,
                score=70.0,
                date=date.today(),
            )
        self.assertTrue(
            StudentResultSummary.objects.filter(
                student=self.student, subject=self.subject, term=self.term
            ).exists()
        )
        with self.captureOnCommitCallbacks(execute=True):
            a.delete()
        self.assertFalse(
            StudentResultSummary.objects.filter(
                student=self.student, subject=self.subject, term=self.term
            ).exists()
        )

    def test_multiple_saves_same_transaction_refresh_once(self):
        calls = []
        real = GradingService.reconcile_student_subject_term_summary

        def spy(student, subject, term):
            calls.append((student.pk, subject.pk, term.pk))
            return real(student, subject, term)

        with mock.patch.object(GradingService, "reconcile_student_subject_term_summary", spy):
            with self.captureOnCommitCallbacks(execute=True):
                for score in (60.0, 62.0):
                    AssessmentScore.objects.update_or_create(
                        student=self.student,
                        subject=self.subject,
                        term=self.term,
                        assessment_type=self.assessment_type,
                        defaults={"score": score, "date": date.today()},
                    )

        key = (self.student.pk, self.subject.pk, self.term.pk)
        self.assertEqual([key], calls)

    def test_collect_triples_for_class_term_and_reconcile(self):
        triples = GradingService.collect_triples_for_class_term(
            self.school, self.term, class_name="P1"
        )
        self.assertEqual(triples, set())

        AssessmentScore.objects.create(
            student=self.student,
            subject=self.subject,
            term=self.term,
            assessment_type=self.assessment_type,
            score=77.0,
            date=date.today(),
        )
        triples = GradingService.collect_triples_for_class_term(
            self.school, self.term, class_name="P1"
        )
        self.assertEqual(triples, {(self.student.pk, self.subject.pk, self.term.pk)})

        ok, err = GradingService.reconcile_triples(triples)
        self.assertEqual(err, 0)
        self.assertEqual(ok, 1)
        summary = StudentResultSummary.objects.get(
            student=self.student, subject=self.subject, term=self.term
        )
        self.assertEqual(summary.ca_score, 77.0)

    def test_collect_triples_by_student_id_matches_class_scope(self):
        AssessmentScore.objects.create(
            student=self.student,
            subject=self.subject,
            term=self.term,
            assessment_type=self.assessment_type,
            score=55.0,
            date=date.today(),
        )
        by_class = GradingService.collect_triples_for_class_term(
            self.school, self.term, class_name="P1"
        )
        by_student = GradingService.collect_triples_for_class_term(
            self.school, self.term, student_id=self.student.pk
        )
        self.assertEqual(by_class, by_student)
        self.assertEqual(
            GradingService.collect_triples_for_class_term(
                self.school, self.term, student_id=0
            ),
            set(),
        )

    def test_collect_triples_subject_id_filter(self):
        sub2 = Subject.objects.create(school=self.school, name="English")
        AssessmentScore.objects.create(
            student=self.student,
            subject=self.subject,
            term=self.term,
            assessment_type=self.assessment_type,
            score=60.0,
            date=date.today(),
        )
        AssessmentScore.objects.create(
            student=self.student,
            subject=sub2,
            term=self.term,
            assessment_type=self.assessment_type,
            score=70.0,
            date=date.today(),
        )
        all_t = GradingService.collect_triples_for_class_term(
            self.school, self.term, class_name="P1"
        )
        self.assertEqual(len(all_t), 2)
        only_math = GradingService.collect_triples_for_class_term(
            self.school, self.term, class_name="P1", subject_id=self.subject.pk
        )
        self.assertEqual(
            only_math, {(self.student.pk, self.subject.pk, self.term.pk)}
        )
        other_school = School.objects.create(
            name="Other", subdomain=f"oth-{uuid.uuid4().hex[:8]}"
        )
        foreign = Subject.objects.create(school=other_school, name="X")
        empty = GradingService.collect_triples_for_class_term(
            self.school, self.term, class_name="P1", subject_id=foreign.pk
        )
        self.assertEqual(empty, set())

    def test_reconcile_result_summaries_command_dry_run(self):
        from io import StringIO

        buf = StringIO()
        call_command(
            "reconcile_result_summaries",
            term_id=self.term.pk,
            class_name="P1",
            dry_run=True,
            stdout=buf,
            verbosity=0,
        )
        self.assertIn("triple", buf.getvalue())

        buf2 = StringIO()
        call_command(
            "reconcile_result_summaries",
            term_id=self.term.pk,
            student_id=self.student.pk,
            dry_run=True,
            stdout=buf2,
            verbosity=0,
        )
        self.assertIn("triple", buf2.getvalue())

    def test_reconcile_command_rejects_foreign_subject(self):
        from django.core.management.base import CommandError

        other = School.objects.create(
            name="Other", subdomain=f"oth-{uuid.uuid4().hex[:8]}"
        )
        foreign = Subject.objects.create(school=other, name="X")
        with self.assertRaises(CommandError):
            call_command(
                "reconcile_result_summaries",
                term_id=self.term.pk,
                class_name="P1",
                subject_id=foreign.pk,
            )

    def test_legacy_result_creates_summary_after_commit(self):
        with self.captureOnCommitCallbacks(execute=True):
            Result.objects.create(
                school=self.school,
                student=self.student,
                subject=self.subject,
                exam_type=self.exam_type,
                term=self.term,
                score=88.0,
                total_score=100.0,
            )
        summary = StudentResultSummary.objects.get(
            student=self.student, subject=self.subject, term=self.term
        )
        self.assertEqual(summary.final_score, 88.0)
        self.assertEqual(summary.ca_score, 0.0)

    def test_modern_scores_take_priority_over_result(self):
        with self.captureOnCommitCallbacks(execute=True):
            Result.objects.create(
                school=self.school,
                student=self.student,
                subject=self.subject,
                exam_type=self.exam_type,
                term=self.term,
                score=50.0,
                total_score=100.0,
            )
        with self.captureOnCommitCallbacks(execute=True):
            AssessmentScore.objects.create(
                student=self.student,
                subject=self.subject,
                term=self.term,
                assessment_type=self.assessment_type,
                score=80.0,
                date=date.today(),
            )
        summary = StudentResultSummary.objects.get(
            student=self.student, subject=self.subject, term=self.term
        )
        self.assertEqual(summary.ca_score, 80.0)
