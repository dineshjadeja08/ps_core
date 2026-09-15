from .base import *  # noqa: F403

import os

import dj_database_url
import sentry_sdk

DEBUG = bool_env("DJANGO_DEBUG", "DEBUG", default=False)  # noqa: F405

if DEBUG:
    raise RuntimeError("DEBUG must be false in production.")

if not os.environ.get("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL must be set in production.")

DATABASES = {
    "default": dj_database_url.config(
        default=os.environ["DATABASE_URL"],
        conn_max_age=600,
        conn_health_checks=True,
    )
}

REDIS_URL = env("REDIS_URL", default="")  # noqa: F405
if not REDIS_URL:
    raise RuntimeError("REDIS_URL must be set in production for shared throttling.")
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 5,
            "IGNORE_EXCEPTIONS": False,
        },
        "KEY_PREFIX": "purple-squad",
        "TIMEOUT": 300,
    }
}

JWT_SIGNING_KEY = env("JWT_SIGNING_KEY", default="")  # noqa: F405
if not JWT_SIGNING_KEY or JWT_SIGNING_KEY == SECRET_KEY:  # noqa: F405
    raise RuntimeError("JWT_SIGNING_KEY must be set to a dedicated production secret.")
SIMPLE_JWT["SIGNING_KEY"] = JWT_SIGNING_KEY  # noqa: F405

if SENTRY_DSN:  # noqa: F405
    sentry_sdk.init(
        dsn=SENTRY_DSN,  # noqa: F405
        environment=SENTRY_ENVIRONMENT,  # noqa: F405
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,  # noqa: F405
        profiles_sample_rate=SENTRY_PROFILES_SAMPLE_RATE,  # noqa: F405
        send_default_pii=False,
    )

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SHOW_API_DOCS = env.bool("SHOW_API_DOCS", default=False)  # noqa: F405
ENABLE_DJANGO_ADMIN = False

if not SENTRY_DSN:  # noqa: F405
    raise RuntimeError("SENTRY_DSN must be set in production for error monitoring.")

if not all(  # noqa: F405
    [
        BACKUP_S3_ENDPOINT_URL,
        BACKUP_S3_BUCKET,
        BACKUP_S3_ACCESS_KEY_ID,
        BACKUP_S3_SECRET_ACCESS_KEY,
    ]
):
    raise RuntimeError("S3-compatible backup storage must be configured in production.")

if SECRET_KEY == "unsafe-local-development-key":  # noqa: F405
    raise RuntimeError("DJANGO_SECRET_KEY must be set in production.")

if not ALLOWED_HOSTS:  # noqa: F405
    raise RuntimeError("ALLOWED_HOSTS must be set in production.")

if not CORS_ALLOWED_ORIGINS:  # noqa: F405
    raise RuntimeError("CORS_ALLOWED_ORIGINS must be set in production.")

if not CSRF_TRUSTED_ORIGINS:  # noqa: F405
    raise RuntimeError("CSRF_TRUSTED_ORIGINS must be set in production.")

if not RAZORPAY_KEY_ID:  # noqa: F405
    raise RuntimeError("RAZORPAY_KEY_ID must be set in production.")

if not RAZORPAY_KEY_SECRET:  # noqa: F405
    raise RuntimeError("RAZORPAY_KEY_SECRET must be set in production.")

if RAZORPAY_ADAPTER.endswith("LocalRazorpayAdapter"):  # noqa: F405
    raise RuntimeError("RAZORPAY_ADAPTER must use RazorpayApiAdapter in production.")

USE_CLOUDINARY_MEDIA = env.bool("USE_CLOUDINARY_MEDIA", default=True)  # noqa: F405
CLOUDINARY_URL = env("CLOUDINARY_URL", default="")  # noqa: F405
CLOUDINARY_CLOUD_NAME = env("CLOUDINARY_CLOUD_NAME", default="")  # noqa: F405
CLOUDINARY_API_KEY = env("CLOUDINARY_API_KEY", default="")  # noqa: F405
CLOUDINARY_API_SECRET = env("CLOUDINARY_API_SECRET", default="")  # noqa: F405

if USE_CLOUDINARY_MEDIA:
    cloudinary_configured = bool(CLOUDINARY_URL) or bool(
        CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET
    )
    if not cloudinary_configured:
        raise RuntimeError("Cloudinary media storage must be configured in production.")

    INSTALLED_APPS += ["cloudinary_storage", "cloudinary"]  # noqa: F405
    STORAGES["default"] = {  # noqa: F405
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    }
    if not CLOUDINARY_URL:
        CLOUDINARY_STORAGE = {
            "CLOUD_NAME": CLOUDINARY_CLOUD_NAME,
            "API_KEY": CLOUDINARY_API_KEY,
            "API_SECRET": CLOUDINARY_API_SECRET,
        }

REQUIRE_OTP_PROVIDER_CONFIG = env.bool("REQUIRE_OTP_PROVIDER_CONFIG", default=False)  # noqa: F405

if REQUIRE_OTP_PROVIDER_CONFIG and OTP_AUTH_PROVIDER.endswith("Msg91OtpProvider"):  # noqa: F405
    if not MSG91_AUTH_KEY:  # noqa: F405
        raise RuntimeError("MSG91_AUTH_KEY must be set in production.")
    if not MSG91_TEMPLATE_ID:  # noqa: F405
        raise RuntimeError("MSG91_TEMPLATE_ID must be set in production.")
    if not MSG91_WHATSAPP_INTEGRATED_NUMBER:  # noqa: F405
        raise RuntimeError("MSG91_WHATSAPP_INTEGRATED_NUMBER must be set in production.")
    if not MSG91_WHATSAPP_TEMPLATE_NAME:  # noqa: F405
        raise RuntimeError("MSG91_WHATSAPP_TEMPLATE_NAME must be set in production.")
    if not MSG91_WHATSAPP_TEMPLATE_NAMESPACE:  # noqa: F405
        raise RuntimeError("MSG91_WHATSAPP_TEMPLATE_NAMESPACE must be set in production.")

if REQUIRE_OTP_PROVIDER_CONFIG and NOTIFICATION_PROVIDER.endswith("Msg91WhatsAppNotificationProvider"):  # noqa: F405
    if not MSG91_WHATSAPP_NOTIFICATION_TEMPLATE_NAME:  # noqa: F405
        raise RuntimeError("MSG91_WHATSAPP_NOTIFICATION_TEMPLATE_NAME must be set in production.")
    if not MSG91_WEBHOOK_SECRET:  # noqa: F405
        raise RuntimeError("MSG91_WEBHOOK_SECRET must be set in production.")

if OTP_AUTH_PROVIDER.endswith("FirebaseAdminAuthProvider") and not (  # noqa: F405
    os.environ.get("FIREBASE_CREDENTIALS_JSON")
    or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
):
    raise RuntimeError("Firebase Admin credentials must be configured server-side in production.")
