"""
Append-only enforcement for audit.AuditLog when settings.AUDIT_APPEND_ONLY is true.

Management commands that must delete rows (prune) use the allow_audit_deletion context manager.
"""

from __future__ import annotations

import threading

from django.conf import settings
from django.db.models.deletion import ProtectedError
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import AuditLog

_tls = threading.local()


def audit_deletion_allowed() -> bool:
    return getattr(_tls, "allow", False)


class allow_audit_deletion:
    """Temporarily allow AuditLog deletes (used by prune_audit_logs only)."""

    def __enter__(self):
        self._prev = getattr(_tls, "allow", False)
        _tls.allow = True
        return self

    def __exit__(self, exc_type, exc, tb):
        _tls.allow = self._prev
        return False


@receiver(pre_delete, sender=AuditLog)
def _prevent_audit_row_delete(sender, instance, **kwargs):
    if not getattr(settings, "AUDIT_APPEND_ONLY", False):
        return
    if audit_deletion_allowed():
        return
    raise ProtectedError(
        "AuditLog rows are append-only (AUDIT_APPEND_ONLY=true). "
        "Archive with archive_audit_logs; optional prune via prune_audit_logs --execute "
        "when AUDIT_PRUNE_ENABLED=true.",
        [instance],
    )
