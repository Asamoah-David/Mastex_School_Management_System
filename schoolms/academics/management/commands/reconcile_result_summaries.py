"""Bulk-repair StudentResultSummary after QuerySet.update / imports / scripts."""

from django.core.management.base import BaseCommand, CommandError

from academics.models import Subject, Term
from academics.services import GradingService
from students.models import Student


class Command(BaseCommand):
    help = (
        "Recompute StudentResultSummary for every student/subject/term in a class "
        "that has AssessmentScore, ExamScore, Result, or an existing summary row. "
        "Use after bulk SQL or QuerySet.update that skipped model signals."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--term-id",
            type=int,
            required=True,
            help="Primary key of academics.Term",
        )
        parser.add_argument(
            "--class-name",
            type=str,
            default="",
            help="Student.class_name (e.g. P1). Required unless --student-id is set.",
        )
        parser.add_argument(
            "--student-id",
            type=int,
            default=None,
            help="Only reconcile triples for this student (must belong to the term's school). "
            "Optional --class-name must match the student's class_name when both are set.",
        )
        parser.add_argument(
            "--school-id",
            type=int,
            default=None,
            help="Optional; must match the term's school if provided",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only print how many triples would be reconciled",
        )
        parser.add_argument(
            "--subject-id",
            type=int,
            default=None,
            help="Only reconcile triples for this subject (must belong to the term's school).",
        )

    def handle(self, *args, **opts):
        term_id = opts["term_id"]
        student_id = opts.get("student_id")
        class_name_raw = (opts.get("class_name") or "").strip()

        try:
            term = Term.objects.select_related("school").get(pk=term_id)
        except Term.DoesNotExist as e:
            raise CommandError(f"Term id={term_id} not found") from e

        school = term.school
        if opts["school_id"] is not None and school.id != opts["school_id"]:
            raise CommandError("Term does not belong to the given --school-id")

        subject_id = opts.get("subject_id")
        if subject_id is not None and not Subject.objects.filter(pk=subject_id, school=school).exists():
            raise CommandError(
                f"Subject id={subject_id} not found for this term's school (id={school.id})"
            )

        if student_id is not None:
            try:
                stu = Student.objects.get(pk=student_id)
            except Student.DoesNotExist as e:
                raise CommandError(f"Student id={student_id} not found") from e
            if stu.school_id != school.id:
                raise CommandError("Student does not belong to the term's school")
            if class_name_raw and stu.class_name and stu.class_name.strip() != class_name_raw:
                raise CommandError(
                    f"Student class_name {stu.class_name!r} does not match --class-name {class_name_raw!r}"
                )
            triples = GradingService.collect_triples_for_class_term(
                school, term, student_id=student_id, subject_id=subject_id
            )
            scope = f"student_id={student_id}"
            if subject_id is not None:
                scope += f", subject_id={subject_id}"
        else:
            if not class_name_raw:
                raise CommandError(
                    "Pass --class-name, or use --student-id for a single student."
                )
            triples = GradingService.collect_triples_for_class_term(
                school, term, class_name=class_name_raw, subject_id=subject_id
            )
            scope = f"class={class_name_raw!r}"
            if subject_id is not None:
                scope += f", subject_id={subject_id}"

        n = len(triples)
        self.stdout.write(
            f"School={school.id} ({school.name!r}) term={term_id} ({scope}): "
            f"{n} distinct student/subject/term triple(s)"
        )
        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — no changes written"))
            return

        ok, err = GradingService.reconcile_triples(triples)
        self.stdout.write(self.style.SUCCESS(f"Reconciled: {ok} ok, {err} error(s)"))
