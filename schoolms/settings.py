import os
import sys
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent  # Points to schoolms/

# Developer Information
DEVELOPER_NAME = "ASAMOAH DAVID"
DEVELOPER_EMAIL = "asamoadavi6917@gmail.com"

# Add schoolms/ to Python path for app imports
sys.path.insert(0, str(BASE_DIR))

load_dotenv()                     # read .env in development

# environment helpers (optional helper function)
def env(name, default=None, required=False):
    val = os.getenv(name, default)
    if required and val is None:
        raise RuntimeError(f"environment variable {name!r} is required")
    return val

SECRET_KEY = env("SECRET_KEY", "unsafe-local-secret")
# Force DEBUG=True for local development unless DATABASE_URL is set (production)
DEBUG = not bool(os.getenv("DATABASE_URL"))

# Always allow localhost and Render; merge with any explicit env values
_required = {"localhost", "127.0.0.1", ".onrender.com"}
_env_hosts = env("ALLOWED_HOSTS", "")
_extra = {h.strip() for h in _env_hosts.split(",") if h.strip()}
ALLOWED_HOSTS = sorted(_required | _extra)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    # custom apps
    "accounts",
    "academics",
    "ai_assistant",
    "fees",
    "finance",
    "messaging",
    # "payments",  # Empty app - disabled to avoid issues
    "schools",
    "services",
    "students",
    "operations",
    "notifications",
    "templatetags.apps.TemplatetagsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "schools.middleware.SchoolMiddleware",
]

ROOT_URLCONF = "schoolms.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "notifications.context_processors.notification_context",
            ],
            "libraries": {
                "custom_filters": "templatetags.custom_filters",
                "feature_flags": "schoolms.templatetags.feature_flags",
            },
        },
    },
]

WSGI_APPLICATION = "schoolms.wsgi.application"

# default database for local dev; overridden by DATABASE_URL below
# Use SQLite for local development (when DEBUG=True), PostgreSQL for production
if DEBUG:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    # Production fallback - use environment variables (recommended: use DATABASE_URL instead)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB", "schoolms"),
            "USER": env("POSTGRES_USER", "postgres"),
            "PASSWORD": env("POSTGRES_PASSWORD", ""),
            "HOST": env("POSTGRES_HOST", "db"),
            "PORT": env("POSTGRES_PORT", "5432"),
        }
    }

AUTH_USER_MODEL = "accounts.User"

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Media files (uploads)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Use BigAutoField by default for primary keys to avoid warnings
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=5),
}

# MNotify
MNOTIFY_API_KEY = env("MNOTIFY_API_KEY", "")
MNOTIFY_SENDER_ID = env("MNOTIFY_SENDER_ID", "")

# Paystack (for school fee payments)
PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY", "")
PAYSTACK_PUBLIC_KEY = env("PAYSTACK_PUBLIC_KEY", "")
PAYSTACK_WEBHOOK_SECRET = env("PAYSTACK_WEBHOOK_SECRET", "")
PAYSTACK_PLATFORM_FEE_PERCENT = float(env("PAYSTACK_PLATFORM_FEE_PERCENT", "0"))  # Commission percentage (0 = no commission)

# Cron job secret key (for securing subscription check endpoint)
CRON_SECRET_KEY = env("CRON_SECRET_KEY", "")

# Google Gemini (AI Assistant) - DEPRECATED, use Groq instead
GEMINI_API_KEY = env("GEMINI_API_KEY", "")

# Groq AI (AI Assistant) - Recommended free tier
GROQ_API_KEY = env("GROQ_API_KEY", "")

# Global admin phone for critical SMS alerts (optional)
ADMIN_PHONE = env("ADMIN_PHONE", "")

# security settings (Render terminates TLS; trust X-Forwarded-Proto)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# CSRF trusted origins
# Prefer explicit configuration via environment variable.
# CSRF_TRUSTED_ORIGINS should be a comma-separated list of full origins,
# e.g. "https://mastex-schoolos.onrender.com,https://app.yourdomain.com".
_csrf_from_env = [
    origin.strip()
    for origin in env("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

CSRF_TRUSTED_ORIGINS = _csrf_from_env

# On Render, RENDER_EXTERNAL_HOSTNAME contains the external hostname
# (e.g. "mastex-schoolos.onrender.com"). Add it automatically if present.
_render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME")
if _render_host:
    CSRF_TRUSTED_ORIGINS.append(f"https://{_render_host}")

# Also trust any hostnames from ALLOWED_HOSTS as HTTPS origins.
# This helps when using a custom domain without setting
# CSRF_TRUSTED_ORIGINS explicitly.
for _host in ALLOWED_HOSTS:
    if not _host or _host in ("localhost", "127.0.0.1"):
        continue
    # Strip a leading dot from wildcard hosts like ".example.com"
    _clean = _host.lstrip(".")
    if "." in _clean:
        origin = f"https://{_clean}"
        if origin not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(origin)

# Only enable security settings in production
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year - enables HTTP Strict Transport Security
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True  # Also protect all subdomains
    SECURE_HSTS_PRELOAD = True  # Allow submission to browser preload lists
else:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_BROWSER_XSS_FILTER = False
    SECURE_CONTENT_TYPE_NOSNIFF = False

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

# Logging configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "ERROR",
    },
    "loggers": {
        "schools": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

# Email configuration
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env("EMAIL_USE_TLS", "True") == "True"
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "noreply@schoolms.com")

# SendGrid API (for email via REST API)
SENDGRID_API_KEY = env("SENDGRID_API_KEY", "")

# Auth redirects
LOGIN_URL = "/accounts/login/"
# Use the smart home route after login to avoid role dashboard loops.
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# Only override with DATABASE_URL in production (when DEBUG=False)
# This allows local development to use SQLite without needing to unset DATABASE_URL
if not DEBUG:
    import dj_database_url
    database_url = os.getenv("DATABASE_URL")
    if database_url and database_url.strip():
        DATABASES["default"] = dj_database_url.config(default=database_url, conn_max_age=600)
