"""
Smoke E2E tests: public endpoints, login, role redirects.

Safe: local SQLite (settings_e2e) only — never point this at production.
"""
from __future__ import annotations

import json
import re

import pytest

pytestmark = pytest.mark.django_db(transaction=True)


def test_health_returns_ok_json(page):
    page.goto("/health/")
    body = page.locator("body").inner_text()
    data = json.loads(body.strip())
    assert data.get("status") == "ok"
    assert data.get("database") in ("ok", "unavailable")


def test_home_loads(page):
    from playwright.sync_api import expect

    page.goto("/")
    expect(page).to_have_title(re.compile(r"Mastex|School|Sign", re.I))


def test_login_page_loads(page):
    from playwright.sync_api import expect

    page.goto("/accounts/login/")
    expect(page.locator("#id_username")).to_be_visible()
    expect(page.locator("#id_password")).to_be_visible()
    expect(page.get_by_role("button", name=re.compile("sign in", re.I))).to_be_visible()


def test_login_rejects_bad_password(e2e_school_admin, page):
    from playwright.sync_api import expect

    page.goto("/accounts/login/")
    page.fill("#id_username", e2e_school_admin.username)
    page.fill("#id_password", "wrong-password-not-real")
    page.get_by_role("button", name=re.compile("sign in", re.I)).click()
    page.wait_for_load_state("networkidle")
    expect(page).to_have_url(re.compile(r"/accounts/login/"))


def test_school_admin_login_reaches_school_dashboard(e2e_school_admin, page):
    from playwright.sync_api import expect

    page.goto("/accounts/login/")
    page.fill("#id_username", e2e_school_admin.username)
    page.fill("#id_password", "E2E-Safe-Login-9x!")
    page.get_by_role("button", name=re.compile("sign in", re.I)).click()
    page.wait_for_url(re.compile(r".*/accounts/school-dashboard/.*"), timeout=15000)
    expect(page).to_have_url(re.compile(r"school-dashboard"))


def test_superuser_login_reaches_dashboard(e2e_superuser, page):
    from playwright.sync_api import expect

    page.goto("/accounts/login/")
    page.fill("#id_username", e2e_superuser.username)
    page.fill("#id_password", "E2E-Super-Login-9x!")
    page.get_by_role("button", name=re.compile("sign in", re.I)).click()
    page.wait_for_url(re.compile(r".*/accounts/dashboard/.*"), timeout=15000)
