"""
Academic Year-End Rollover command.

Performs the end-of-year transition for a given school:
  1. Archives the current AcademicYear and all its Terms (is_current → False, is_archived → True).
  2. Promotes active students to the next class (if a promotion map is configured, or the
     configured default "move up by level" strategy).
  3. Graduates students in the final class (sets status = 'graduated', creates Alumni record).
  4. Creates the new AcademicYear and first Term if requested.
  5. Rolls overdue FeeInstallmentPlans to 'overdue' status.

Usage:
    python manage.py year_end_rollover --school <school_id>
    python manage.py year_end_rollover --school <school_id> --create-new-year --year-name "2026/2027"
    python manage.py year_end_rollover --school <school_id> --dry-run

Options:
    --school        School pk (required).
    --dry-run       Print what would happen without committing changes.
    --create-new-year   Create a new AcademicYear row after archiving the current one.
    --year-name     Name for the new AcademicYear, e.g. '2026/2027'.
    --graduate-class    Name of the final class whose students should be graduated (e.g. 'Form 6').
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Year-end rollover: archive current academic year/terms, promote students, "
        "graduate final-year students, and optionally create the next academic year."
    )

    def add_arguments(self, parser):
        parser.add_argument("--school", type=int, required=True, help="School primary key.")
        parser.add_argument("--dry-run", action="store_true", default=False, help="Preview without writing.")
        parser.add_argument("--create-new-year", action="store_true", default=False,
                            help="Create a new AcademicYear after archiving the current one.")
        parser.add_argument("--year-name", type=str, default="",
                            help="Name for the new academic year (e.g. '2026/2027').")
        parser.add_argument("--graduate-class", type=str, default="",
                            help="Class name whose active students will be graduated (e.g. 'Form 6').")

    def handle(self, *args, **options):
        from schools.models import School
        from academics.models import AcademicYear, Term
        from students.models import Student, SchoolClass
        from operations.models import Alumni
        from finance.models import FeeInstallmentPlan
        from django.db import transaction

        school_id = options["school"]
        dry_run = options["dry_run"]
        create_new_year = options["create_new_year"]
        new_year_name = options["year_name"].strip()
        graduate_class_name = options["graduate_class"].strip()
        now = timezone.now()
        today = now.date()

        try:
            school = School.objects.get(pk=school_id)
        except School.DoesNotExist:
            raise CommandError(f"School with pk={school_id} does not exist.")

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n{'[DRY RUN] ' if dry_run else ''}Year-End Rollover — {school.name} (pk={school_id})\n"
        ))

        stats = {
            "terms_archived": 0,
            "years_archived": 0,
            "students_promoted": 0,
            "students_graduated": 0,
            "installments_overdue": 0,
            "new_year_created": False,
        }

        with transaction.atomic():
            # ------------------------------------------------------------------
            # Step 1: Archive current Terms
            # ------------------------------------------------------------------
            current_terms = Term.objects.filter(school=school, is_current=True)
            for term in current_terms:
                self.stdout.write(f"  Archiving Term: {term.name}")
                if not dry_run:
                    term.is_current = False
                    if hasattr(term, "is_archived"):
                        term.is_archived = True
                    term.save()
                stats["terms_archived"] += 1

            # ------------------------------------------------------------------
            # Step 2: Archive current AcademicYear
            # ------------------------------------------------------------------
            current_year = AcademicYear.objects.filter(school=school, is_current=True).first()
            if current_year:
                self.stdout.write(f"  Archiving Academic Year: {current_year.name}")
                if not dry_run:
                    current_year.is_current = False
                    if hasattr(current_year, "is_archived"):
                        current_year.is_archived = True
                    current_year.save()
                stats["years_archived"] = 1

            # ------------------------------------------------------------------
            # Step 3: Graduate final-year students
            # ------------------------------------------------------------------
            if graduate_class_name:
                final_class_qs = SchoolClass.objects.filter(school=school, name__iexact=graduate_class_name)
                for final_class in final_class_qs:
                    final_students = Student.objects.filter(
                        school=school, school_class=final_class,
                        status="active", deleted_at__isnull=True,
                    )
                    for student in final_students:
                        self.stdout.write(
                            f"  Graduating: {student.user.get_full_name()} (class: {final_class.name})"
                        )
                        if not dry_run:
                            student.status = "graduated"
                            student.exit_date = today
                            student.exit_reason = "graduated"
                            student.save(update_fields=["status", "exit_date", "exit_reason"])

                            # Create Alumni record if not already present
                            if not Alumni.objects.filter(school=school, student=student).exists():
                                Alumni.objects.create(
                                    school=school,
                                    student=student,
                                    first_name=student.user.first_name,
                                    last_name=student.user.last_name,
                                    admission_number=student.admission_number,
                                    class_name=final_class.name,
                                    school_class=final_class,
                                    graduation_year=today.year,
                                    graduation_date=today,
                                    is_active_member=True,
                                )
                        stats["students_graduated"] += 1

            # ------------------------------------------------------------------
            # Step 4: Promote remaining active students to next class
            # ------------------------------------------------------------------
            # Strategy: sort all school classes by name alphabetically and
            # move each student to the next class in the ordered list.
            # Students whose current class is the last (or the graduate class)
            # are skipped here (they were handled above).
            classes = list(
                SchoolClass.objects.filter(school=school).order_by("name").values_list("pk", "name")
            )
            class_order = {pk: idx for idx, (pk, _) in enumerate(classes)}
            class_by_idx = {idx: pk for idx, (pk, _) in enumerate(classes)}
            graduate_pks = set(
                SchoolClass.objects.filter(
                    school=school, name__iexact=graduate_class_name
                ).values_list("pk", flat=True)
            ) if graduate_class_name else set()

            students_to_promote = Student.objects.filter(
                school=school, status="active", deleted_at__isnull=True,
                school_class__isnull=False,
            ).exclude(school_class__in=graduate_pks)

            for student in students_to_promote:
                current_idx = class_order.get(student.school_class_id)
                if current_idx is None:
                    continue
                next_idx = current_idx + 1
                next_class_pk = class_by_idx.get(next_idx)
                if next_class_pk is None:
                    continue
                next_class = SchoolClass.objects.get(pk=next_class_pk)
                self.stdout.write(
                    f"  Promoting: {student.user.get_full_name()} → {next_class.name}"
                )
                if not dry_run:
                    student.school_class = next_class
                    student.class_name = next_class.name
                    student.save(update_fields=["school_class", "class_name"])
                stats["students_promoted"] += 1

            # ------------------------------------------------------------------
            # Step 5: Mark overdue FeeInstallmentPlans
            # ------------------------------------------------------------------
            overdue_qs = FeeInstallmentPlan.objects.filter(
                school=school, due_date__lt=today, status__in=["pending", "partial"],
            )
            cnt = overdue_qs.count()
            if cnt:
                self.stdout.write(f"  Marking {cnt} installments as overdue")
                if not dry_run:
                    overdue_qs.update(status="overdue")
            stats["installments_overdue"] = cnt

            # ------------------------------------------------------------------
            # Step 6: Create new AcademicYear (optional)
            # ------------------------------------------------------------------
            if create_new_year:
                if not new_year_name:
                    if current_year:
                        parts = current_year.name.split("/")
                        if len(parts) == 2:
                            try:
                                new_year_name = f"{int(parts[0])+1}/{int(parts[1])+1}"
                            except ValueError:
                                new_year_name = f"New Year after {current_year.name}"
                        else:
                            new_year_name = f"After {current_year.name}"
                    else:
                        new_year_name = str(today.year + 1)

                if not AcademicYear.objects.filter(school=school, name=new_year_name).exists():
                    self.stdout.write(f"  Creating new AcademicYear: {new_year_name}")
                    if not dry_run:
                        from datetime import date
                        year_num = today.year + 1
                        AcademicYear.objects.create(
                            school=school,
                            name=new_year_name,
                            start_date=date(year_num, 9, 1),
                            end_date=date(year_num + 1, 7, 31),
                            is_current=True,
                        )
                    stats["new_year_created"] = True
                else:
                    self.stdout.write(
                        self.style.WARNING(f"  AcademicYear '{new_year_name}' already exists — skipped.")
                    )

            if dry_run:
                transaction.set_rollback(True)

        # ------------------------------------------------------------------
        # Summary
        # ------------------------------------------------------------------
        self.stdout.write("\n" + self.style.SUCCESS("  Rollover Summary:"))
        self.stdout.write(f"    Terms archived        : {stats['terms_archived']}")
        self.stdout.write(f"    Years archived        : {stats['years_archived']}")
        self.stdout.write(f"    Students promoted     : {stats['students_promoted']}")
        self.stdout.write(f"    Students graduated    : {stats['students_graduated']}")
        self.stdout.write(f"    Installments overdue  : {stats['installments_overdue']}")
        self.stdout.write(f"    New year created      : {'Yes' if stats['new_year_created'] else 'No'}")
        if dry_run:
            self.stdout.write(self.style.WARNING("\n  [DRY RUN] — No changes were committed.\n"))
        else:
            self.stdout.write(self.style.SUCCESS("\n  Rollover complete.\n"))
