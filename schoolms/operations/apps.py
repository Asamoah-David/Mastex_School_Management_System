from django.apps import AppConfig


class OperationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "operations"
    verbose_name = "School Operations (Attendance, Canteen, Bus, Textbooks)"

    def ready(self):
        # Register auth → ActivityLog signal handlers
        from operations import signals  # noqa: F401
        # Register Budget.spent_amount auto-sync signals
        from operations.models import finance  # noqa: F401
