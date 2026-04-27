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

# ---------------------------------------------------------------------------
# HTTPS / HSTS — only active in production (when DEBUG=False)
# W004, W008, W012, W016, W018 are suppressed in dev automatically because
# all of these require DEBUG=False to matter.
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", default=True)
    SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", default="31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True)
    SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", default=False)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"

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

# Tenant subdomain resolution (schools.middleware.SchoolMiddleware)
# Only hosts ending with one of these suffixes will be treated as tenant hosts.
# Examples: ".onrender.com", ".railway.app".
TENANT_DOMAIN_SUFFIXES = tuple(h for h in ALLOWED_HOSTS if isinstance(h, str) and h.startswith("."))

# Canonical domain for SEO and consistency (non-www redirects to www)
CANONICAL_DOMAIN = env("CANONICAL_DOMAIN", "mastexedu.online")

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
    "django_celery_beat",
    # Project apps
    "core",
    "accounts",
    "academics",
    "ai_assistant",
    "audit",
    "integrations",
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
    "django.middleware.gzip.GZipMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "core.middleware.CanonicalDomainMiddleware",
    "core.middleware.RequestIdMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.CspMiddleware",
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
        "accounts.context_processors.current_datetime",
        "schools.context_processors.school_feature_flags",
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
                conn_max_age=0,
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
                "CONN_MAX_AGE": 0,
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
        "school_api": "200/minute",
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
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.URLPathVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ["v1"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "MastexEDU API",
    "DESCRIPTION": "MastexEDU School Management Platform — REST API",
    "VERSION": "2.0.0",
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
    _cors_debug_origins = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
    ]
    CORS_ALLOWED_ORIGINS = list(set(CORS_ALLOWED_ORIGINS + _cors_debug_origins))

# ---------------------------------------------------------------------------
# Third-party service keys
# ---------------------------------------------------------------------------
MNOTIFY_API_KEY = env("MNOTIFY_API_KEY", "")
MNOTIFY_SENDER_ID = env("MNOTIFY_SENDER_ID", "")

# Admission SMS: optional short public origin for links (e.g. https://school.example.com) when
# the incoming Host header is long or internal. If unset, links use the current request URL.
_admission_sms_base = env("ADMISSION_SMS_PUBLIC_BASE_URL", "").strip()
if _admission_sms_base and not _admission_sms_base.startswith(("http://", "https://")):
    _admission_sms_base = f"https://{_admission_sms_base}"
ADMISSION_SMS_PUBLIC_BASE_URL = _admission_sms_base or None
try:
    ADMISSION_SMS_MAX_CHARS = max(120, min(640, int(env("ADMISSION_SMS_MAX_CHARS", "300"))))
except ValueError:
    ADMISSION_SMS_MAX_CHARS = 300
# SMS when an admission application moves along the pipeline (requires SMS gateway).
ADMISSION_STATUS_SMS_ENABLED = env_bool("ADMISSION_STATUS_SMS_ENABLED", True)

try:
    BULK_IN_APP_NOTIFICATION_CAP = max(100, min(5000, int(env("BULK_IN_APP_NOTIFICATION_CAP", "1500"))))
except ValueError:
    BULK_IN_APP_NOTIFICATION_CAP = 1500

# Hard ceiling for any SMS body (after optional [school] prefix in SMSService); avoids huge payloads.
try:
    SMS_MESSAGE_HARD_MAX_CHARS = max(500, int(env("SMS_MESSAGE_HARD_MAX_CHARS", "2500")))
except ValueError:
    SMS_MESSAGE_HARD_MAX_CHARS = 2500

PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY", "")
PAYSTACK_PUBLIC_KEY = env("PAYSTACK_PUBLIC_KEY", "")
# Optional override. Paystack signs webhooks with HMAC-SHA512 using your API Secret Key
# (Dashboard → Settings → API Keys & Webhooks — there is no separate “webhook secret” value).
PAYSTACK_WEBHOOK_SECRET = env("PAYSTACK_WEBHOOK_SECRET", "")
PAYSTACK_WEBHOOK_SIGNING_SECRET = PAYSTACK_WEBHOOK_SECRET or PAYSTACK_SECRET_KEY
PAYSTACK_PLATFORM_FEE_PERCENT = float(env("PAYSTACK_PLATFORM_FEE_PERCENT", "0"))
PAYSTACK_CURRENCY = env("PAYSTACK_CURRENCY", "GHS")
# Uplift charged to payer so settlement ≈ net after Paystack's % (tune PAYSTACK_PROCESSING_FEE_PERCENT to match pricing).
PAYSTACK_PASS_FEE_TO_PAYER = env_bool("PAYSTACK_PASS_FEE_TO_PAYER", True)
PAYSTACK_PROCESSING_FEE_PERCENT = env_float("PAYSTACK_PROCESSING_FEE_PERCENT", 1.95)
# Outgoing staff salary transfers via Paystack (debits Paystack merchant balance, not subaccounts).
PAYSTACK_STAFF_TRANSFERS_ENABLED = env_bool("PAYSTACK_STAFF_TRANSFERS_ENABLED", False)
# Keep automated staff payouts off unless school-owned funding controls are implemented and validated.
PAYSTACK_STAFF_SCHOOL_OWNED_PAYOUTS_READY = env_bool("PAYSTACK_STAFF_SCHOOL_OWNED_PAYOUTS_READY", False)

# Days after subscription_end_date before school users are fully locked out (per-school override on School.subscription_grace_days).
SUBSCRIPTION_DEFAULT_GRACE_DAYS = int(env("SUBSCRIPTION_DEFAULT_GRACE_DAYS", "7"))

CRON_SECRET_KEY = env("CRON_SECRET_KEY", "")

# Outbound HTTPS webhooks (integrations.SchoolWebhookEndpoint) — staff leave & expenses.
INTEGRATIONS_WEBHOOKS_ENABLED = env_bool("INTEGRATIONS_WEBHOOKS_ENABLED", True)
try:
    INTEGRATIONS_WEBHOOK_TIMEOUT_SEC = max(3, min(60, int(env("INTEGRATIONS_WEBHOOK_TIMEOUT_SEC", "10"))))
except ValueError:
    INTEGRATIONS_WEBHOOK_TIMEOUT_SEC = 10

# ---------------------------------------------------------------------------
# Compliance: model audit trail (audit.AuditLog)
# ---------------------------------------------------------------------------
# Production default: append-only (no admin/ORM deletes). Opt out with AUDIT_APPEND_ONLY=0.
# Local dev (DEBUG=True): default off so fixtures and experiments stay easy.
AUDIT_APPEND_ONLY = env_bool("AUDIT_APPEND_ONLY", not DEBUG)
# Prune command refuses to run deletes unless this is true or --force is passed.
AUDIT_PRUNE_ENABLED = env_bool("AUDIT_PRUNE_ENABLED", False)
_audit_ret = env("AUDIT_RETENTION_DAYS", "").strip()
try:
    AUDIT_RETENTION_DAYS = int(_audit_ret) if _audit_ret else None
except ValueError:
    AUDIT_RETENTION_DAYS = None
AUDIT_ARCHIVE_DIR = Path(env("AUDIT_ARCHIVE_DIR", str(BASE_DIR / "var" / "audit_archive"))).resolve()

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
# Exposed for management commands (e.g. preflight) — TLS terminated at load balancer / PaaS edge.
BEHIND_TLS_TERMINATING_PROXY = _tls_terminating_proxy

# Number of trusted reverse proxies in front of the app (used for IP extraction).
# Railway/Render add 1 hop; set to 2 if behind Cloudflare + platform proxy.
NUM_PROXIES = int(env("NUM_PROXIES", "1"))

# Trust X-Forwarded-Host header from Railway proxy for custom domain handling
USE_X_FORWARDED_HOST = True

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

# TLS is at the edge; SECURE_SSL_REDIRECT stays False so in-container probes are not 301'd.
SILENCED_SYSTEM_CHECKS = []
if not DEBUG and _tls_terminating_proxy:
    SILENCED_SYSTEM_CHECKS.append("security.W008")

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 12  # 12 hours
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = False
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"

DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 500

# ---------------------------------------------------------------------------
# Password Validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
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
# Production: JSON lines on stdout for log aggregation; override with LOG_JSON=0.
_log_json_stdout = env_bool("LOG_JSON", not DEBUG)

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

# ---------------------------------------------------------------------------
# Celery (async task queue)
# ---------------------------------------------------------------------------
# Broker: use Redis when available; fall back to in-memory (dev only — tasks are LOST on restart).
_celery_broker = env("CELERY_BROKER_URL", _redis_url or "memory://")
if _celery_broker == "memory://" and not DEBUG:
    import logging as _logging
    _logging.getLogger("django").critical(
        "CELERY_BROKER_URL is 'memory://' in a non-DEBUG environment. "
        "Tasks (fee reminders, webhooks, PDF generation) will be lost on worker restart. "
        "Set CELERY_BROKER_URL=redis://... in your environment."
    )
CELERY_BROKER_URL = _celery_broker
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", _redis_url or "cache+memory://")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = env("TIME_ZONE", "Africa/Accra")
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300  # 5 minutes hard limit per task
CELERY_TASK_SOFT_TIME_LIMIT = 240
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# Static periodic tasks — picked up by Celery Beat on startup.
# Can be overridden per-school via the Django admin (django-celery-beat).
CELERY_BEAT_SCHEDULE = {
    "inventory-low-stock-alerts-daily": {
        "task": "core.tasks.send_inventory_low_stock_alerts",
        "schedule": 86400,  # every 24 hours
    },
    "fee-payment-reminders-daily": {
        "task": "core.tasks.send_fee_payment_reminders",
        "schedule": 86400,
        "kwargs": {"days_before_due": 3},
    },
    "paystack-settlement-reconciliation-daily": {
        "task": "core.tasks.reconcile_paystack_settlements",
        "schedule": 86400,
    },
    "leave-balance-rollover-yearly": {
        "task": "core.tasks.rollover_leave_balances",
        "schedule": 86400 * 30,  # monthly check; actual rollover is idempotent
        # from_year/to_year default to None; the task derives current/next year automatically
    },
    "subscription-auto-expiry-daily": {
        "task": "core.tasks.auto_expire_subscriptions",
        "schedule": 86400,
    },
    "mark-overdue-installments-daily": {
        "task": "core.tasks.mark_overdue_installments",
        "schedule": 86400,
    },
    "auto-expire-staff-contracts-daily": {
        "task": "core.tasks.auto_expire_staff_contracts",
        "schedule": 86400,
    },
    "retry-failed-webhooks-every-15min": {
        "task": "core.tasks.retry_failed_webhook_deliveries",
        "schedule": 900,
    },
    "fixed-asset-depreciation-yearly": {
        "task": "core.tasks.apply_fixed_asset_depreciation_annual",
        "schedule": 86400 * 365,
    },
    # DB-6: purge expired in-app notifications weekly
    "purge-expired-notifications-weekly": {
        "task": "core.tasks.purge_expired_notifications",
        "schedule": 86400 * 7,
    },
    # ENH-4: flag students with 3+ consecutive absences daily
    "attendance-early-warning-daily": {
        "task": "core.tasks.flag_attendance_early_warnings",
        "schedule": 86400,
    },
}
