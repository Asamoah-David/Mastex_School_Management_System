from django.core.management.base import BaseCommand

from accounts.hr_utils import sync_expired_staff_contracts
from schools.models import School


class Command(BaseCommand):
    help = "Mark active staff contracts as expired when their end_date has passed (run daily via cron)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school-id",
            type=int,
            default=None,
            help="Limit to one school (default: all schools).",
        )

    def handle(self, *args, **options):
        sid = options["school_id"]
        school = School.objects.filter(pk=sid).first() if sid else None
        if sid and not school:
            self.stderr.write(self.style.ERROR(f"No school with id={sid}."))
            return
        n = sync_expired_staff_contracts(school=school)
        self.stdout.write(self.style.SUCCESS(f"Marked {n} staff contract(s) as expired."))
