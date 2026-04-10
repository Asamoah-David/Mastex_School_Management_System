import logging
import os
import sys
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(BASE_DIR))

load_dotenv()


def env(name, default=None, required=False, cast=None):
    val = os.getenv(name, default)
    if required and val is None:
        raise RuntimeError(f"Environment variable {name!r} is required but not set")
    if val is not None and cast is not None:
        val = cast(val)
    return val


def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in ("1", "true", "yes")


def env_float(name, default):
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return float(default)


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
# On Railway/Render/Fly, default DEBUG off if unset (avoids accidental prod debug).
_platform_detected = bool(
    os.getenv("RAILWAY_ENVIRONMENT")
    or os.getenv("RAILWAY_PROJECT_ID")
    or os.getenv("RENDER")
    or os.getenv("RENDER_EXTERNAL_HOSTNAME")
    or os.getenv("FLY_APP_NAME")
)
DEBUG = env_bool("DEBUG", default=not _platform_detected)

SECRET_KEY = env("SECRET_KEY", default="unsafe-local-secret" if DEBUG else None)
if not DEBUG and SECRET_KEY == "unsafe-local-secret":
    raise RuntimeError(
        "SECRET_KEY must be set to a strong random value in production. "
        "Generate one with: python -c \"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())\""
    )

_required_hosts = {
    "localhost",
    "127.0.0.1",
    ".onrender.com",
    ".railway.app",
    ".up.railway.app",
}
_env_hosts = {h.strip() for h in env("ALLOWED_HOSTS", "").split(",") if h.strip()}
ALLOWED_HOSTS = sorted(_required_hosts | _env_hosts)

# ---------------------------------------------------------------------------
# Apps & Middleware
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    # Project apps
    "core",
    "accounts",
    "academics",
    "ai_assistant",
    "audit",
    "fees",
    "finance",
    "messaging",
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
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "schools.middleware.SchoolMiddleware",
    "accounts.middleware.ForcePasswordChangeMiddleware",
    "audit.middleware.AuditUserMiddleware",
]

ROOT_URLCONF = "schoolms.urls"

_template_options = {
    "context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "notifications.context_processors.notification_context",
        "accounts.context_processors.role_permissions",
    ],
    "libraries": {
        "custom_filters": "templatetags.custom_filters",
        "feature_flags": "schoolms.templatetags.feature_flags",
        "qr_utils": "templatetags.qr_utils",
    },
}

if not DEBUG:
    _template_options["loaders"] = [
        (
            "django.template.loaders.cached.Loader",
            [
                "django.template.loaders.filesystem.Loader",
                "django.template.loaders.app_directories.Loader",
            ],
        ),
    ]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        **({"APP_DIRS": True} if DEBUG else {}),
        "OPTIONS": _template_options,
    },
]

WSGI_APPLICATION = "schoolms.wsgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
if DEBUG and not os.getenv("DATABASE_URL"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    import dj_database_url

    _db_url = os.getenv("DATABASE_URL")
    if _db_url:
        DATABASES = {
            "default": dj_database_url.config(
                default=_db_url,
                conn_max_age=600,
                conn_health_checks=True,
            )
        }
    else:
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": env("POSTGRES_DB", "schoolms"),
                "USER": env("POSTGRES_USER", "postgres"),
                "PASSWORD": env("POSTGRES_PASSWORD", ""),
                "HOST": env("POSTGRES_HOST", "db"),
                "PORT": env("POSTGRES_PORT", "5432"),
                "CONN_MAX_AGE": 600,
                "CONN_HEALTH_CHECKS": True,
            }
        }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------
_redis_url = os.getenv("REDIS_URL", "")

if _redis_url:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": _redis_url,
            "TIMEOUT": 300,
            "KEY_PREFIX": "sms",
            "OPTIONS": {"socket_connect_timeout": 2},
        }
    }
    SESSION_ENGINE = "django.contrib.sessions.backends.cache"
elif not DEBUG:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "django_cache_table",
            "TIMEOUT": 300,
            "OPTIONS": {"MAX_ENTRIES": 10000},
        }
    }
    SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }

# ---------------------------------------------------------------------------
# Static & Media
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = "/media/"
_persistent_paths = [Path("/app/media"), Path("/var/data/media")]
MEDIA_ROOT = next(
    (p for p in _persistent_paths if p.exists()),
    BASE_DIR / "media",
)

# ---------------------------------------------------------------------------
# REST Framework & JWT
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/minute",
        "user": "300/minute",
    },
    "DEFAULT_RENDERER_CLASSES": (
        ["rest_framework.renderers.JSONRenderer"]
        if not DEBUG
        else [
            "rest_framework.renderers.JSONRenderer",
            "rest_framework.renderers.BrowsableAPIRenderer",
        ]
    ),
    "EXCEPTION_HANDLER": "rest_framework.views.exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Mastex SchoolOS API",
    "DESCRIPTION": "School Management System API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_SETTINGS": {"persistAuthorization": True},
    # Who can hit /api/schema/, /api/docs/, /api/redoc/ (see API_DOCS_* below)
    "SERVE_AUTHENTICATION": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
}

# OpenAPI / Swagger: off entirely, or authenticated-only in production (default).
API_DOCS_ENABLED = env_bool("API_DOCS_ENABLED", True)
# When False with DEBUG off, schema is only reachable by logged-in users (session or Bearer JWT).
API_DOCS_PUBLIC = env_bool("API_DOCS_PUBLIC", DEBUG)
if API_DOCS_PUBLIC:
    SPECTACULAR_SETTINGS["SERVE_PERMISSIONS"] = [
        "rest_framework.permissions.AllowAny",
    ]
else:
    SPECTACULAR_SETTINGS["SERVE_PERMISSIONS"] = [
        "rest_framework.permissions.IsAuthenticated",
    ]

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "UPDATE_LAST_LOGIN": True,
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in env("CORS_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]
CORS_ALLOW_CREDENTIALS = True
if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True

# ---------------------------------------------------------------------------
# Third-party service keys
# ---------------------------------------------------------------------------
MNOTIFY_API_KEY = env("MNOTIFY_API_KEY", "")
MNOTIFY_SENDER_ID = env("MNOTIFY_SENDER_ID", "")

PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY", "")
PAYSTACK_PUBLIC_KEY = env("PAYSTACK_PUBLIC_KEY", "")
PAYSTACK_WEBHOOK_SECRET = env("PAYSTACK_WEBHOOK_SECRET", "")
PAYSTACK_PLATFORM_FEE_PERCENT = float(env("PAYSTACK_PLATFORM_FEE_PERCENT", "0"))
PAYSTACK_CURRENCY = env("PAYSTACK_CURRENCY", "GHS")
# Uplift charged to payer so settlement ≈ net after Paystack's % (tune PAYSTACK_PROCESSING_FEE_PERCENT to match pricing).
PAYSTACK_PASS_FEE_TO_PAYER = env_bool("PAYSTACK_PASS_FEE_TO_PAYER", True)
PAYSTACK_PROCESSING_FEE_PERCENT = env_float("PAYSTACK_PROCESSING_FEE_PERCENT", 1.95)

CRON_SECRET_KEY = env("CRON_SECRET_KEY", "")

SUPABASE_URL = env("SUPABASE_URL", "")
SUPABASE_ANON_KEY = env("SUPABASE_ANON_KEY", "")
SUPABASE_STORAGE_BUCKET = env("SUPABASE_STORAGE_BUCKET", "media")

GEMINI_API_KEY = env("GEMINI_API_KEY", "")
GROQ_API_KEY = env("GROQ_API_KEY", "")
ADMIN_PHONE = env("ADMIN_PHONE", "")

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

_csrf_from_env = [
    origin.strip()
    for origin in env("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
CSRF_TRUSTED_ORIGINS = _csrf_from_env

_render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME")
if _render_host:
    CSRF_TRUSTED_ORIGINS.append(f"https://{_render_host}")

for _host in ALLOWED_HOSTS:
    if not _host or _host in ("localhost", "127.0.0.1"):
        continue
    _clean = _host.lstrip(".")
    if "." in _clean:
        origin = f"https://{_clean}"
        if origin not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(origin)

# TLS is terminated at the platform edge (Railway, Render, Fly). In-container
# probes (e.g. Railway → http://0.0.0.0:PORT/health/) have no
# X-Forwarded-Proto; SECURE_SSL_REDIRECT would 301 every healthcheck and fail deploys.
_tls_terminating_proxy = bool(
    os.getenv("RAILWAY_ENVIRONMENT")
    or os.getenv("RAILWAY_PROJECT_ID")
    or os.getenv("RENDER")
    or os.getenv("RENDER_EXTERNAL_HOSTNAME")
    or os.getenv("FLY_APP_NAME")
    or env_bool("BEHIND_TLS_TERMINATING_PROXY", False)
)

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool(
        "SECURE_SSL_REDIRECT",
        not _tls_terminating_proxy,
    )
    SECURE_HSTS_SECONDS = 31_536_000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
    SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
    PERMISSIONS_POLICY = {
        "accelerometer": [],
        "camera": [],
        "geolocation": [],
        "microphone": [],
    }
    CSP_DEFAULT_SRC = ("'self'",)
    CSP_SCRIPT_SRC = ("'self'", "https://js.paystack.co",)
    CSP_STYLE_SRC = ("'self'", "'unsafe-inline'", "https://fonts.googleapis.com",)
    CSP_FONT_SRC = ("'self'", "https://fonts.gstatic.com",)
    CSP_IMG_SRC = ("'self'", "data:", "https:",)
    CSP_CONNECT_SRC = ("'self'", "https://api.paystack.co",)
    CSP_FRAME_SRC = ("'none'",)
    CSP_OBJECT_SRC = ("'none'",)
    CSP_BASE_URI = ("'self'",)
    CSP_FORM_ACTION = ("'self'",)
else:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 12  # 12 hours
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = False
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"

DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 5000

# ---------------------------------------------------------------------------
# Password Validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
_log_handlers = ["console"]

_LOG_DIR = BASE_DIR / "logs"
_use_file_log = False
try:
    _LOG_DIR.mkdir(exist_ok=True)
    _use_file_log = True
    _log_handlers.append("file")
except OSError:
    pass

_root_log_level = env("LOG_LEVEL", "DEBUG" if DEBUG else "INFO").upper()
_app_log_level = env("APP_LOG_LEVEL", _root_log_level).upper()
_log_json_stdout = env_bool("LOG_JSON", False)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {module}:{lineno} {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "simple": {
            "format": "{levelname} {name}: {message}",
            "style": "{",
        },
        "json": {
            "()": "schoolms.logging_utils.JsonLinesFormatter",
        },
    },
    "filters": {
        "require_debug_false": {"()": "django.utils.log.RequireDebugFalse"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json"
            if _log_json_stdout
            else ("verbose" if not DEBUG else "simple"),
        },
        **(
            {
                "file": {
                    "level": "WARNING",
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": str(_LOG_DIR / "app.log"),
                    "maxBytes": 10 * 1024 * 1024,  # 10 MB
                    "backupCount": 5,
                    "formatter": "verbose",
                }
            }
            if _use_file_log
            else {}
        ),
        "mail_admins": {
            "level": "ERROR",
            "filters": ["require_debug_false"],
            "class": "django.utils.log.AdminEmailHandler",
        },
    },
    "root": {
        "handlers": _log_handlers,
        "level": _root_log_level,
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": _root_log_level,
            "propagate": False,
        },
        "django.security": {
            "handlers": _log_handlers + ["mail_admins"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.request": {
            "handlers": _log_handlers + ["mail_admins"],
            "level": "ERROR",
            "propagate": False,
        },
        **{
            app: {
                "handlers": _log_handlers,
                "level": _app_log_level,
                "propagate": False,
            }
            for app in [
                "schools",
                "core",
                "accounts",
                "academics",
                "finance",
                "operations",
                "messaging",
                "students",
                "notifications",
                "audit",
            ]
        },
    },
}

# ---------------------------------------------------------------------------
# Sentry (production error tracking)
# ---------------------------------------------------------------------------
SENTRY_DSN = env("SENTRY_DSN", "")
SENTRY_TRACES_SAMPLE_RATE = env_float("SENTRY_TRACES_SAMPLE_RATE", 0.1)
SENTRY_PROFILES_SAMPLE_RATE = env_float("SENTRY_PROFILES_SAMPLE_RATE", 0.0)

if SENTRY_DSN and not DEBUG:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    def _sentry_before_send(event, hint):
        req = event.get("request") or {}
        url = req.get("url") or ""
        if "/health/" in url or url.rstrip("/").endswith("/health"):
            return None
        return event

    def _sentry_traces_sampler(sampling_context):
        wsgi = sampling_context.get("wsgi_environ") or {}
        path = wsgi.get("PATH_INFO") or ""
        if path == "/health/" or path.rstrip("/").endswith("/health"):
            return 0
        return max(0.0, min(1.0, SENTRY_TRACES_SAMPLE_RATE))

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(
                transaction_style="url",
                middleware_spans=True,
                signals_spans=False,
            ),
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR,
            ),
        ],
        traces_sampler=_sentry_traces_sampler,
        profiles_sample_rate=max(0.0, min(1.0, SENTRY_PROFILES_SAMPLE_RATE)),
        send_default_pii=False,
        environment=env("SENTRY_ENVIRONMENT", "production"),
        release=env("GIT_COMMIT_SHA", "") or None,
        before_send=_sentry_before_send,
    )

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env("EMAIL_BACKEND", "core.email_backends.SendGridEmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "noreply@schoolms.com")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
SENDGRID_API_KEY = env("SENDGRID_API_KEY", "")

ADMINS = [
    (env("ADMIN_NAME", "Admin"), env("ADMIN_EMAIL", DEFAULT_FROM_EMAIL)),
]

# ---------------------------------------------------------------------------
# Auth redirects
# ---------------------------------------------------------------------------
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
