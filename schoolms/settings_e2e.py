"""
Django settings for browser E2E tests (Playwright).

Uses SQLite and in-memory-ish cache so tests run without Postgres/Redis.
Do not use in production.
"""
import os

# Base ``settings`` evaluates DEBUG (and the whole ``if not DEBUG`` security/template block) during
# import. GHA sets DEBUG=False for the e2e job; that enables production template loaders, CSP,
# Secure cookies, etc. Playwright uses plain http:// live_server — session/CSRF then break.
# Must override CI's DEBUG=False (and wins over .env because we set the env before load_dotenv).
os.environ["DEBUG"] = "True"

# noqa: F401,F403 — re-export base settings then override
from schoolms.settings import *  # noqa: F401,F403,E402

DEBUG = True
SECRET_KEY = "e2e-playwright-not-for-production"

# Belt-and-suspenders if anything re-reads production defaults after import.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

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
