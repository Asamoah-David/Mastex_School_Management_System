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


class SchoolScopedManager(models.Manager):
    def get_queryset(self) -> SchoolScopedQuerySet:
        return SchoolScopedQuerySet(self.model, using=self._db)

    def for_school(self, school) -> SchoolScopedQuerySet:
        return self.get_queryset().for_school(school)


def school_id_from(school) -> Optional[int]:
    if school is None:
        return None
    sid = getattr(school, "pk", None) or getattr(school, "id", None)
    try:
        return int(sid) if sid is not None else None
    except (TypeError, ValueError):
        return None
