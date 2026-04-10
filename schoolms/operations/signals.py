"""Signals that populate operations.ActivityLog."""

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

from operations.activity import client_ip_from_request, log_school_activity


@receiver(user_logged_in)
def activity_log_login(sender, request, user, **kwargs):
    log_school_activity(
        user=user,
        action="login",
        details="Signed in successfully.",
        ip=client_ip_from_request(request),
    )


@receiver(user_logged_out)
def activity_log_logout(sender, request, user, **kwargs):
    u = user if user is not None and getattr(user, "pk", None) else None
    log_school_activity(
        user=u,
        action="logout",
        details="Signed out.",
        ip=client_ip_from_request(request),
    )
