from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'audit'
    verbose_name = 'Audit Logging'

    def ready(self):
        """Connect audit signals when the app is ready."""
        # Import signals to register receivers
        from . import signals
        from . import protection  # noqa: F401 — registers append-only pre_delete
