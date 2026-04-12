"""
Django settings for browser E2E tests (Playwright).

Uses SQLite and in-memory-ish cache so tests run without Postgres/Redis.
Do not use in production.
"""
# noqa: F401,F403 — re-export base settings then override
from schoolms.settings import *  # noqa: F401,F403

DEBUG = True
SECRET_KEY = "e2e-playwright-not-for-production"

# Base settings may enable ERP flags when DEBUG is false at import time; force test-friendly values.
AUDIT_APPEND_ONLY = False
AUDIT_PRUNE_ENABLED = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "e2e_test.sqlite3",
        # live_server runs in a thread; SQLite can briefly lock on Linux CI without a longer wait.
        "OPTIONS": {"timeout": 30},
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
SESSION_ENGINE = "django.contrib.sessions.backends.db"
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Faster password hashing for test DB only
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

_hosts = set(ALLOWED_HOSTS) | {"testserver"}
ALLOWED_HOSTS = sorted(_hosts)
