"""
Idempotent demo data for handbook screenshot capture.

Only intended for disposable SQLite DBs used by capture_handbook_screenshots.
Refuses to run against non-SQLite unless --force is passed.
"""

from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from accounts.models import User
from finance.models import Fee, FeeStructure
from notifications.models import Notification
from schools.models import School
from students.models import SchoolClass, Student

DEMO_SUBDOMAIN = "handbookdemo"
ADMIN_USERNAME = "handbook_admin"
PARENT_USERNAME = "handbook_parent"
STUDENT_USERNAME = "handbook_student"
DEFAULT_PASSWORD = "HandbookDemo2026!"


class Command(BaseCommand):
    help = "Create demo school, users, student, fees, and sample notifications for handbook captures."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow running when the default database is not SQLite (unsafe on production).",
        )
        parser.add_argument(
            "--password",
            default=DEFAULT_PASSWORD,
            help="Password for handbook_admin, handbook_parent, and handbook_student (default: built-in demo password).",
        )

    def handle(self, *args, **options):
        if connection.vendor != "sqlite" and not options["force"]:
            raise CommandError(
                "handbook_seed_demo targets a disposable SQLite database. "
                "Use capture_handbook_screenshots (temp SQLite) or pass --force if you "
                "really want to seed your current database."
            )

        password = options["password"]
        now = timezone.now()

        school, _ = School.objects.update_or_create(
            subdomain=DEMO_SUBDOMAIN,
            defaults={
                "name": "Riverside Academy (Handbook Demo)",
                "email": "demo-handbook@mastexedu.online",
                "phone": "+233544789716",
                "is_active": True,
                "subscription_status": "active",
                "subscription_start_date": now - timedelta(days=30),
                "subscription_end_date": now + timedelta(days=365),
                "academic_year": "2025/2026",
            },
        )

        admin, _ = User.objects.update_or_create(
            username=ADMIN_USERNAME,
            defaults={
                "email": "handbook-admin@mastexedu.online",
                "first_name": "Demo",
                "last_name": "Administrator",
                "role": "school_admin",
                "school": school,
                "password": make_password(password),
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
            },
        )

        parent, _ = User.objects.update_or_create(
            username=PARENT_USERNAME,
            defaults={
                "email": "handbook-parent@mastexedu.online",
                "first_name": "Demo",
                "last_name": "Parent",
                "role": "parent",
                "school": school,
                "password": make_password(password),
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
            },
        )

        stu_user, _ = User.objects.update_or_create(
            username=STUDENT_USERNAME,
            defaults={
                "email": "handbook-student@mastexedu.online",
                "first_name": "Ama",
                "last_name": "Mensah",
                "role": "student",
                "gender": "female",
                "school": school,
                "password": make_password(password),
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
            },
        )

        klass, _ = SchoolClass.objects.get_or_create(
            school=school,
            name="Form 1A",
            defaults={"capacity": 40},
        )

        student, _ = Student.objects.update_or_create(
            user=stu_user,
            defaults={
                "school": school,
                "admission_number": "HB-DEMO-001",
                "class_name": "Form 1A",
                "school_class": klass,
                "parent": parent,
                "status": "active",
            },
        )

        fs, _ = FeeStructure.objects.get_or_create(
            school=school,
            name="Term 2 Tuition (Demo)",
            class_name="Form 1A",
            defaults={"amount": 1200.00, "is_active": True},
        )

        fee = Fee.objects.filter(student=student, fee_structure=fs).first()
        if not fee:
            Fee.objects.create(
                school=school,
                student=student,
                fee_structure=fs,
                amount=1200.00,
                amount_paid=0,
            )

        Notification.objects.filter(
            user=admin, title__startswith="[Handbook]"
        ).delete()
        Notification.create_notification(
            admin,
            "[Handbook] Fee payment recorded",
            "GHS 100.00 applied to Term 2 tuition (demo).",
            notification_type="payment",
            include_school=False,
        )
        Notification.create_notification(
            admin,
            "[Handbook] PTA meeting reminder",
            "Thursday 6pm - hall (demo).",
            notification_type="info",
            include_school=False,
        )
        Notification.create_notification(
            admin,
            "[Handbook] Homework due",
            "Mathematics - submit online (demo).",
            notification_type="info",
            include_school=False,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Handbook demo data ready. School subdomain={DEMO_SUBDOMAIN!r}; "
                f"log in as {ADMIN_USERNAME!r} or {PARENT_USERNAME!r} (same password)."
            )
        )
