import os
import sys
from datetime import timedelta
from pathlib import Path

import dj_database_url
import recurrence


def _env_int(name, default):
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_float(name, default):
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


BASE_DIR = Path(__file__).resolve().parent.parent
KIOSK_AGENT_WHEEL_DIR = Path(
    os.environ.get("KIOSK_AGENT_WHEEL_DIR", BASE_DIR / "agent-dist")
)

EXECUTION_MODE = os.environ.get("EXECUTION_MODE", "run")
ENVIRONMENT = os.environ.get("STAGE", "local")
DEBUG = os.environ.get("DEBUG", "").lower() == "true"

SITE_BASE_PATH = os.environ.get("SITE_BASE_PATH", "").rstrip("/")
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "").rstrip("/")
FORCE_SCRIPT_NAME = SITE_BASE_PATH or None
USE_X_FORWARDED_HOST = True

if EXECUTION_MODE == "build":
    SECRET_KEY = "build-only-secret-key-never-used-at-runtime"  # noqa: S105
    ALLOWED_HOSTS = ["example.com"]
else:
    SECRET_KEY = os.environ["SECRET_KEY"]
    ALLOWED_HOSTS = [
        host.strip()
        for host in os.environ.get(
            "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1"
        ).split(",")
        if host.strip()
    ]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

INSTALLED_APPS = [
    "adminutils",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.messages",
    "django_celery_results",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "ninja",
    "kiosk_manager.apps.DefaultConfig",
    "kiosk_manager.kiosks.apps.KiosksConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

ROOT_URLCONF = "kiosk_manager.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "debug": DEBUG,
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "kiosk_manager.wsgi.application"
ASGI_APPLICATION = "kiosk_manager.asgi.application"

if EXECUTION_MODE == "build":
    DATABASES = {}
else:
    database_dsn = os.environ.get("DEFAULT_DATABASE_DSN") or os.environ.get(
        "DATABASE_URL"
    )
    if not database_dsn:
        raise RuntimeError("DEFAULT_DATABASE_DSN must be configured")

    DATABASES = {
        "default": dj_database_url.parse(
            database_dsn,
            conn_max_age=60,
            conn_health_checks=True,
        )
    }
    DATABASES["default"]["ATOMIC_REQUESTS"] = True

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = f"{SITE_BASE_PATH}/media/"
STATIC_URL = f"{SITE_BASE_PATH}/static/"
WHITENOISE_STATIC_PREFIX = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "static",
    Path(recurrence.__file__).resolve().parent / "static",
]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            or (EXECUTION_MODE != "build" and ENVIRONMENT in {"local", "test"})
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CELERY_BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL",
    os.environ.get("BROKER_URL", "amqp://kiosk:kiosk@rabbitmq:5672//"),
)
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "django-db")
CELERY_BROKER_CONNECTION_MAX_RETRIES = None
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_TRACK_STARTED = True
CELERY_WORKER_MAX_TASKS_PER_CHILD = 128
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_ENABLE_REMOTE_CONTROL = False
CELERY_WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS = True
CELERY_BEAT_SCHEDULE_FILENAME = str(
    BASE_DIR / ".artifacts" / "celerybeat-schedule"
)
CELERY_TIMEZONE = TIME_ZONE
EVENT_RETENTION_DAYS = _env_int("EVENT_RETENTION_DAYS", 30)
CELERY_BEAT_SCHEDULE = {
    "delete-expired-kiosk-events": {
        "task": "kiosk_manager.kiosks.tasks.delete_expired_events",
        "schedule": timedelta(days=1),
    },
}

ADMIN_SITE_HEADER = "Kiosk Manager Administration"
ADMIN_SITE_TITLE = "Kiosk Manager Admin"
ADMIN_INDEX_TITLE = "Administration"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_COOKIES = os.environ.get("SECURE_COOKIES", "true").lower() == "true"
SESSION_COOKIE_SECURE = SECURE_COOKIES
SESSION_COOKIE_NAME = "kiosk_manager_sessionid"
CSRF_COOKIE_SECURE = SECURE_COOKIES
CSRF_COOKIE_NAME = "kiosk_manager_csrftoken"
SECURE_SSL_REDIRECT = (
    os.environ.get(
        "SECURE_SSL_REDIRECT",
        str(ENVIRONMENT == "live" or EXECUTION_MODE == "build"),
    ).lower()
    == "true"
)
SECURE_HSTS_SECONDS = _env_int(
    "SECURE_HSTS_SECONDS", 31536000 if not DEBUG else 0
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = (
    os.environ.get("SECURE_HSTS_INCLUDE_SUBDOMAINS", str(not DEBUG)).lower()
    == "true"
)
SECURE_HSTS_PRELOAD = (
    os.environ.get("SECURE_HSTS_PRELOAD", str(not DEBUG)).lower() == "true"
)

SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
SENTRY_ENVIRONMENT = os.environ.get(
    "SENTRY_ENVIRONMENT", f"kiosk-manager-{ENVIRONMENT}"
)
SENTRY_TRACES_SAMPLE_RATE = _env_float("SENTRY_TRACES_SAMPLE_RATE", 0)
SENTRY_PROFILES_SAMPLE_RATE = _env_float("SENTRY_PROFILES_SAMPLE_RATE", 0)
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT,
        release=os.environ.get("GIT_COMMIT", os.environ.get("GIT_BRANCH")),
        integrations=[DjangoIntegration(), CeleryIntegration()],
        send_default_pii=False,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        profiles_sample_rate=SENTRY_PROFILES_SAMPLE_RATE,
    )

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "{levelname}/{processName}/{name}.{funcName}:{lineno} {message}",
            "style": "{",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "stream": sys.stdout,
            "formatter": "simple",
        }
    },
    "loggers": {
        "": {"handlers": ["console"], "level": "INFO"},
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.server": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "py.warnings": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
