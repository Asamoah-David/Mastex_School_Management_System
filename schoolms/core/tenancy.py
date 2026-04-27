from __future__ import annotations

from typing import Optional

from django.db import models


class SchoolScopedQuerySet(models.QuerySet):
    def for_school(self, school) -> "SchoolScopedQuerySet":
        if school is None:
            return self.none()
        school_id = getattr(school, "pk", None) or getattr(school, "id", None)
        if school_id is None:
            return self.none()
        return self.filter(school_id=school_id)

    def active_students(self) -> "SchoolScopedQuerySet":
        """Convenience: filter to status='active' (only meaningful on Student QS)."""
        return self.filter(status="active")


class SchoolScopedManager(models.Manager):
    def get_queryset(self) -> SchoolScopedQuerySet:
        return SchoolScopedQuerySet(self.model, using=self._db)

    def for_school(self, school) -> SchoolScopedQuerySet:
        return self.get_queryset().for_school(school)


class UnscopedManager(models.Manager):
    """Unrestricted manager — use only in migrations, admin, and super-admin views."""

    def get_queryset(self) -> models.QuerySet:
        return super().get_queryset()


class SchoolScopedModel(models.Model):
    """Abstract base class for any model that belongs to a single school tenant.

    Provides:
      - ``objects`` — default manager returning a SchoolScopedQuerySet (supports
        ``.for_school(school)``).
      - ``unscoped`` — unrestricted manager for admin / migrations / super-admin only.

    Concrete models must define ``school = models.ForeignKey(School, ...)``.
    """

    objects = SchoolScopedManager()
    unscoped = UnscopedManager()

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    def delete(self):
        from django.utils import timezone
        return self.update(deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()

    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def deleted(self):
        return self.filter(deleted_at__isnull=False)


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).alive()

    def all_with_deleted(self):
        return SoftDeleteQuerySet(self.model, using=self._db)

    def deleted_only(self):
        return SoftDeleteQuerySet(self.model, using=self._db).deleted()


class SoftDeleteModel(models.Model):
    """Mixin that replaces hard delete with a ``deleted_at`` timestamp.

    Apply to Student, Fee, Result so historical records survive accidental
    deletion. Managers expose ``.all_with_deleted()`` and ``.deleted_only()``.
    """
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = SoftDeleteManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        from django.utils import timezone
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])

    def hard_delete(self, using=None, keep_parents=False):
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        self.deleted_at = None
        self.save(update_fields=["deleted_at"])

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


def school_id_from(school) -> Optional[int]:
    if school is None:
        return None
    sid = getattr(school, "pk", None) or getattr(school, "id", None)
    try:
        return int(sid) if sid is not None else None
    except (TypeError, ValueError):
        return None
