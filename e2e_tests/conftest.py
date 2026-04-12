"""
Fixtures for smoke tests (``schoolms.settings_e2e``).

Uses the ``db`` fixture: tests run in-process with Django's test client (no live_server).
"""
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from schools.models import School

pytest_plugins = ["pytest_django"]


@pytest.fixture
def e2e_school(db):
    end = timezone.now() + timedelta(days=60)
    return School.objects.create(
        name="E2E Test School",
        subdomain="e2e-test-school",
        subscription_status="active",
        subscription_end_date=end,
        is_active=True,
    )


@pytest.fixture
def e2e_school_admin(db, e2e_school):
    User = get_user_model()
    return User.objects.create_user(
        username="e2e_school_admin",
        password="E2E-Safe-Login-9x!",
        school=e2e_school,
        role="school_admin",
        must_change_password=False,
    )


@pytest.fixture
def e2e_superuser(db):
    User = get_user_model()
    u = User.objects.create_user(
        username="e2e_superuser",
        password="E2E-Super-Login-9x!",
        role="super_admin",
        must_change_password=False,
    )
    u.is_superuser = True
    u.is_staff = True
    u.save(update_fields=["is_superuser", "is_staff"])
    return u
