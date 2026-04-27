from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from threading import local
import logging

from .models import AuditLog

logger = logging.getLogger(__name__)

_thread_locals = local()


def get_current_user():
    """Get current user from thread-local storage (set by AuditUserMiddleware)."""
    return getattr(_thread_locals, 'user', None)


def set_current_user(user):
    """Set current user in thread-local storage (called by AuditUserMiddleware)."""
    _thread_locals.user = user


class AuditSignalHandler:
    """Handler for automatic model auditing."""

    _excluded_model_names = frozenset([
        'auditlog', 'session', 'logentry', 'permission', 'contenttype',
        'migration', 'webhookdeliveryattempt', 'conversationhistory',
        'notificationpreference',
    ])
    _excluded_app_labels = frozenset([
        'admin', 'auth', 'contenttypes', 'sessions', 'django_celery_beat',
        'django_celery_results',
    ])
    # Only audit changes to fields that matter (exclude volatile bookkeeping)
    _skip_fields = frozenset(['updated_at', 'last_login', 'total_tokens'])

    @classmethod
    def get_model_name(cls, instance):
        return f"{instance._meta.app_label}.{instance._meta.model_name}"

    @classmethod
    def should_audit(cls, instance):
        if instance._meta.model_name in cls._excluded_model_names:
            return False
        if instance._meta.app_label in cls._excluded_app_labels:
            return False
        return True

    @classmethod
    def get_school(cls, instance):
        if hasattr(instance, 'school_id'):
            sid = instance.school_id
            if sid:
                try:
                    from schools.models import School
                    return School.objects.only('pk', 'name').get(pk=sid)
                except Exception:
                    pass
        return None

    @classmethod
    def log_action(cls, action, instance, user=None, changes=None, request=None):
        try:
            AuditLog.log_action(
                user=user,
                action=action,
                model_name=cls.get_model_name(instance),
                object_id=instance.pk,
                object_repr=repr_safe(instance),
                changes=changes or {},
                request=request,
                school=cls.get_school(instance)
            )
        except Exception as e:
            logger.error("Failed to log audit action: %s", e)


def repr_safe(instance):
    """Get a string representation without triggering extra FK queries."""
    try:
        model = instance._meta.label
        return f"{model} #{instance.pk}"
    except Exception:
        return str(instance.pk)


@receiver(pre_save, dispatch_uid='audit_pre_save_global')
def audit_pre_save(sender, instance, **kwargs):
    """Capture field changes using _loaded_values only (no extra DB query)."""
    if not AuditSignalHandler.should_audit(instance):
        return
    if not instance.pk:
        return

    # Only diff when the queryset already stored _loaded_values (from .from_db)
    # Avoids the expensive per-save SELECT that was previously issued.
    db_values = getattr(instance, '_loaded_values', None)
    if not db_values:
        return

    try:
        changes = {}
        skip = AuditSignalHandler._skip_fields | {'password'}
        for field in instance._meta.fields:
            if field.name in skip:
                continue
            attname = field.attname
            new_val = getattr(instance, attname, None)
            old_val = db_values.get(attname)
            if old_val != new_val:
                changes[field.name] = {'old': str(old_val), 'new': str(new_val)}
        if changes:
            instance._audit_changes = changes
    except Exception as e:
        logger.error("Audit pre_save signal error: %s", e)


@receiver(post_save, dispatch_uid='audit_post_save_global')
def audit_post_save(sender, instance, created, **kwargs):
    if not AuditSignalHandler.should_audit(instance):
        return

    try:
        user = get_current_user()

        if created:
            AuditSignalHandler.log_action('create', instance, user=user)
        else:
            changes = getattr(instance, '_audit_changes', None)
            if changes:
                AuditSignalHandler.log_action('update', instance, user=user, changes=changes)
                del instance._audit_changes
    except Exception as e:
        logger.error("Audit save signal error: %s", e)


@receiver(post_delete, dispatch_uid='audit_post_delete_global')
def audit_post_delete(sender, instance, **kwargs):
    if not AuditSignalHandler.should_audit(instance):
        return

    try:
        user = get_current_user()
        AuditSignalHandler.log_action('delete', instance, user=user)
    except Exception as e:
        logger.error("Audit delete signal error: %s", e)
