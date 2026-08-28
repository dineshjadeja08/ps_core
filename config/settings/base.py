import os
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")

def csv_env(*names, default=None, strip_trailing_slash=False):
    for name in names:
        raw_value = os.environ.get(name)
        if raw_value is not None:
            values = [item.strip() for item in raw_value.split(",") if item.strip()]
            if strip_trailing_slash:
                return [value.rstrip("/") for value in values]
            return values
    return default or []


def bool_env(*names, default=False):
    truthy = {"1", "true", "t", "yes", "y", "on"}
    falsy = {"0", "false", "f", "no", "n", "off"}
    for name in names:
        raw_value = os.environ.get(name)
        if raw_value is None:
            continue
        normalized = raw_value.strip().lower()
        if normalized in truthy:
            return True
        if normalized in falsy:
            return False
        raise RuntimeError(f"{name} must be a boolean value.")
    return default


def string_env(*names, default=""):
    for name in names:
        raw_value = os.environ.get(name)
        if raw_value is not None:
            return raw_value.strip()
    return default


SECRET_KEY = string_env("DJANGO_SECRET_KEY", "SECRET_KEY", default="unsafe-local-development-key")
DEBUG = bool_env("DJANGO_DEBUG", "DEBUG", default=False)
ALLOWED_HOSTS = csv_env("DJANGO_ALLOWED_HOSTS", "ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "apps.accounts",
    "apps.catalogue",
    "apps.locations",
    "apps.scheduling",
    "apps.bookings",
    "apps.payments",
    "apps.technicians",
    "apps.reviews",
    "apps.notifications",
    "apps.audit",
    "common",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "common.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'dev.sqlite3'}",
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

CORS_ALLOWED_ORIGINS = csv_env("CORS_ALLOWED_ORIGINS", strip_trailing_slash=True)
CSRF_TRUSTED_ORIGINS = csv_env("CSRF_TRUSTED_ORIGINS", strip_trailing_slash=True)

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "common.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "common.exceptions.standard_exception_handler",
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("DRF_THROTTLE_ANON", default="100/min"),
        "user": env("DRF_THROTTLE_USER", default="1000/min"),
        "auth": env("DRF_THROTTLE_AUTH", default="10/min"),
        "payment": env("DRF_THROTTLE_PAYMENT", default="30/min"),
        "webhook": env("DRF_THROTTLE_WEBHOOK", default="120/min"),
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Purple Squad API",
    "DESCRIPTION": "API for the Purple Squad home services platform.",
    "VERSION": "v1",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

SIMPLE_JWT = {
    "AUTH_HEADER_TYPES": ("Bearer",),
}

FIREBASE_AUTH_PROVIDER = env(
    "FIREBASE_AUTH_PROVIDER",
    default="apps.accounts.auth.providers.FirebaseAdminAuthProvider",
)
OTP_AUTH_PROVIDER = env("OTP_AUTH_PROVIDER", default="apps.accounts.otp.providers.Msg91OtpProvider")
MSG91_AUTH_KEY = env("MSG91_AUTH_KEY", default="")
MSG91_TEMPLATE_ID = env("MSG91_TEMPLATE_ID", default="")
MSG91_SEND_OTP_URL = env("MSG91_SEND_OTP_URL", default="https://control.msg91.com/api/v5/otp")
MSG91_VERIFY_OTP_URL = env("MSG91_VERIFY_OTP_URL", default="https://control.msg91.com/api/v5/otp/verify")
MSG91_OTP_EXPIRY_MINUTES = env.int("MSG91_OTP_EXPIRY_MINUTES", default=5)
DEV_PHONE_LOGIN_ENABLED = env.bool("DEV_PHONE_LOGIN_ENABLED", default=False)
DEV_PHONE_LOGIN_ALLOWED_NUMBERS = env.list("DEV_PHONE_LOGIN_ALLOWED_NUMBERS", default=[])
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", default="")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", default="test_razorpay_secret")
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET", default="test_razorpay_webhook_secret")
RAZORPAY_ADAPTER = env("RAZORPAY_ADAPTER", default="apps.payments.providers.LocalRazorpayAdapter")

BOOKING_CUSTOMER_CANCEL_MIN_HOURS = env.int("BOOKING_CUSTOMER_CANCEL_MIN_HOURS", default=2)
BOOKING_CUSTOMER_RESCHEDULE_MIN_HOURS = env.int("BOOKING_CUSTOMER_RESCHEDULE_MIN_HOURS", default=4)
BOOKING_REQUIRE_BALANCE_BEFORE_COMPLETION = env.bool("BOOKING_REQUIRE_BALANCE_BEFORE_COMPLETION", default=True)
NOTIFICATION_PROVIDER = env(
    "NOTIFICATION_PROVIDER",
    default="apps.notifications.providers.LocalNotificationProvider",
)
SHOW_API_DOCS = env.bool("SHOW_API_DOCS", default=DEBUG)

REQUEST_ID_HEADER = env("REQUEST_ID_HEADER", default="HTTP_X_REQUEST_ID")
LOG_LEVEL = env("LOG_LEVEL", default="INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "format": (
                '{"timestamp":"%(asctime)s","level":"%(levelname)s",'
                '"logger":"%(name)s","message":"%(message)s"}'
            )
        }
    },
    "filters": {
        "redact_sensitive": {
            "()": "common.logging.RedactSensitiveLogFilter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
            "filters": ["redact_sensitive"],
        }
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
}
