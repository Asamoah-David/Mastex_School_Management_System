from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
import logging

from .models import AuditLog

logger = logging.getLogger(__name__)


class AuditSignalHandler:
    """Handler for automatic model auditing."""
    
    # Models to exclude from automatic auditing
    EXCLUDED_MODELS = [
        'Session',
        'LogEntry',
        'Permission',
        'ContentType',
        'AuditLog',
    ]
    
    # Track original values for update detection
    _original_values = {}
    
    @classmethod
    def get_model_name(cls, instance):
        """Get the model name from an instance."""
        return f"{instance._meta.app_label}.{instance._meta.model_name}"
    
    @classmethod
    def should_audit(cls, instance):
        """Check if the model should be audited."""
        model_name = cls.get_model_name(instance)
        # Don't audit if model is in excluded list or is AuditLog itself
        if instance._meta.model_name in ['auditlog', 'session', 'logentry', 'permission', 'contenttype']:
            return False
        # Don't audit admin models
        if instance._meta.app_label in ['admin', 'auth']:
            return False
        return True
    
    @classmethod
    def get_school(cls, instance):
        """Get school from the instance if available."""
        if hasattr(instance, 'school'):
            return instance.school
        return None
    
    @classmethod
    def log_action(cls, action, instance, user=None, changes=None, request=None):
        """Log an audit action."""
        try:
            AuditLog.log_action(
                user=user,
                action=action,
                model_name=cls.get_model_name(instance),
                object_id=instance.pk,
                object_repr=str(instance),
                changes=changes or {},
                request=request,
                school=cls.get_school(instance)
            )
        except Exception as e:
            logger.error(f"Failed to log audit action: {e}")


def get_current_user():
    """Get current user from request context."""
    try:
        from django.contrib.auth import get_user_model
        from threading import local
        _thread_locals = local()
        return getattr(_thread_locals, 'user', None)
    except:
        return None


# CONNECT SIGNALS - These decorators actually connect the functions to Django signals
@receiver(pre_save)
def audit_pre_save(sender, instance, **kwargs):
    """Signal receiver to capture original values before save."""
    if not AuditSignalHandler.should_audit(instance):
        return
    
    if instance.pk:
        try:
            # Get the original instance from database
            original = sender.objects.get(pk=instance.pk)
            changes = {}
            
            # Compare field values
            for field in instance._meta.fields:
                if field.name in ['password']:  # Don't log password changes
                    continue
                old_val = getattr(original, field.name, None)
                new_val = getattr(instance, field.name, None)
                if old_val != new_val:
                    changes[field.name] = {'old': str(old_val), 'new': str(new_val)}
            
            if changes:
                AuditSignalHandler._original_values[id(instance)] = changes
        except sender.DoesNotExist:
            pass
        except Exception as e:
            logger.error(f"Audit pre_save signal error: {e}")


@receiver(post_save)
def audit_post_save(sender, instance, created, **kwargs):
    """Signal receiver for model save events."""
    if not AuditSignalHandler.should_audit(sender):
        return
    
    try:
        user = get_current_user()
        
        if created:
            AuditSignalHandler.log_action('create', instance, user=user)
        else:
            # Get changes from pre_save signal
            changes = AuditSignalHandler._original_values.pop(id(instance), {})
            if changes:
                AuditSignalHandler.log_action('update', instance, user=user, changes=changes)
    except Exception as e:
        logger.error(f"Audit save signal error: {e}")


@receiver(post_delete)
def audit_post_delete(sender, instance, **kwargs):
    """Signal receiver for model delete events."""
    if not AuditSignalHandler.should_audit(instance):
        return
    
    try:
        user = get_current_user()
        AuditSignalHandler.log_action('delete', instance, user=user)
    except Exception as e:
        logger.error(f"Audit delete signal error: {e}")
