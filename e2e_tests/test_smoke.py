"""
Smoke tests: public endpoints, login, role redirects.

Uses Django's test client (same process as DB) so CI is stable without a browser.
Playwright was repeatedly flaky on GitHub-hosted Linux runners (live_server, cookies, IPv6).

Safe: ``schoolms.settings_e2e`` (SQLite under project root, gitignored) — never point at production.
"""
from __future__ import annotations

import json
import re

import pytest

pytestmark = pytest.mark.django_db


def test_health_returns_ok_json(client):
    r = client.get("/health/")
    assert r.status_code == 200
    data = json.loads(r.content.decode())
    assert data.get("status") == "ok"
    assert data.get("database") in ("ok", "unavailable")


def test_home_loads(client):
    r = client.get("/")
    assert r.status_code == 200
    html = r.content.decode().lower()
    assert re.search(r"mastex|school|sign", html)


def test_login_page_loads(client):
    r = client.get("/accounts/login/")
    assert r.status_code == 200
    html = r.content.decode().lower()
    assert 'id="id_username"' in html or "id_username" in html
    assert 'id="id_password"' in html or "id_password" in html
    assert "sign in" in html


def test_login_rejects_bad_password(client, e2e_school_admin):
    r = client.post(
        "/accounts/login/",
        {"username": e2e_school_admin.username, "password": "wrong-password-not-real"},
    )
    assert r.status_code == 200
    assert b"id_username" in r.content


def test_school_admin_login_reaches_school_dashboard(client, e2e_school_admin):
    r = client.post(
        "/accounts/login/",
        {"username": e2e_school_admin.username, "password": "E2E-Safe-Login-9x!"},
    )
    assert r.status_code == 302
    assert "school-dashboard" in r["Location"]


def test_superuser_login_reaches_dashboard(client, e2e_superuser):
    r = client.post(
        "/accounts/login/",
        {"username": e2e_superuser.username, "password": "E2E-Super-Login-9x!"},
    )
    assert r.status_code == 302
    assert "dashboard" in r["Location"]
    assert "school-dashboard" not in r["Location"].lower()
