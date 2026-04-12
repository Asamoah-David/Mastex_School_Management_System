"""
Django live server + Playwright.

Playwright is **function-scoped** only so the asyncio proactor is not started
during session setup (which would break pytest-django's DB creation on Windows).

In tests, list ORM fixtures (e.g. ``e2e_school_admin``) **before** ``page``:
pytest sets up parameters left-to-right, and Playwright must start after DB data exists.
"""
import os

# Default live_server host is "localhost"; on Linux that often resolves to ::1 while the
# thread binds 127.0.0.1 — Playwright then misses the server and tests time out.
os.environ.setdefault("DJANGO_LIVE_TEST_SERVER_ADDRESS", "127.0.0.1:0")

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from schools.models import School

pytest_plugins = ["pytest_django"]


@pytest.fixture
def page(live_server):
    from playwright.sync_api import sync_playwright

    launch_args = []
    if os.environ.get("CI"):
        # GitHub Actions / Linux runners: default Chromium sandbox often fails headless.
        launch_args.extend(["--no-sandbox", "--disable-dev-shm-usage"])

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=launch_args)
        context = browser.new_context(base_url=live_server.url)
        pg = context.new_page()
        try:
            yield pg
        finally:
            context.close()
            browser.close()


@pytest.fixture
def e2e_school(transactional_db):
    end = timezone.now() + timedelta(days=60)
    return School.objects.create(
        name="E2E Test School",
        subdomain="e2e-test-school",
        subscription_status="active",
        subscription_end_date=end,
        is_active=True,
    )


@pytest.fixture
def e2e_school_admin(transactional_db, e2e_school):
    User = get_user_model()
    return User.objects.create_user(
        username="e2e_school_admin",
        password="E2E-Safe-Login-9x!",
        school=e2e_school,
        role="school_admin",
        must_change_password=False,
    )


@pytest.fixture
def e2e_superuser(transactional_db):
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
