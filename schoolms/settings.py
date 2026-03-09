import os
import sys
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent  # Points to schoolms/

# Developer Information
DEVELOPER_NAME = "ASAMOAH DAVID"
DEVELOPER_EMAIL = "asamoadavi6917@6917"

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
    "payments",
    "schools",
    "services",
    "students",
    "operations",
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
            ],
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
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "schoolms",
            "USER": "postgres",
            "PASSWORD": "postgres",
            "HOST": "db",
            "PORT": "5432",
        }
    }

AUTH_USER_MODEL = "accounts.User"

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

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

# Stripe
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", "")
STRIPE_PUBLIC_KEY = env("STRIPE_PUBLIC_KEY", "")
STRIPE_PRICE_ID = env("STRIPE_PRICE_ID", "")

# MNotify
MNOTIFY_API_KEY = env("MNOTIFY_API_KEY", "")
MNOTIFY_SENDER_ID = env("MNOTIFY_SENDER_ID", "")

# Flutterwave
FLW_PUBLIC_KEY = env("FLW_PUBLIC_KEY", "")
FLW_SECRET_KEY = env("FLW_SECRET_KEY", "")
FLW_WEBHOOK_SECRET = env("FLW_WEBHOOK_SECRET", "")

# OpenAI
OPENAI_API_KEY = env("OPENAI_API_KEY", "")

# security settings (Render terminates TLS; trust X-Forwarded-Proto)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Required for POST requests (admin login, forms) behind Render's HTTPS
# Add any custom ALLOWED_HOSTS to CSRF_TRUSTED_ORIGINS
_csrf_origins = {f"https://{host}" for host in ALLOWED_HOSTS if host not in {"localhost", "127.0.0.1"}}
CSRF_TRUSTED_ORIGINS = sorted(_csrf_origins | {f"https://{h}.onrender.com" for h in ALLOWED_HOSTS if ".onrender.com" in h})

# Only enable security settings in production
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
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

# Auth redirects
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# override with DATABASE_URL (Render provides this in production)
import dj_database_url

database_url = os.getenv("DATABASE_URL")
if database_url and database_url.strip():
    DATABASES["default"] = dj_database_url.config(default=database_url)
