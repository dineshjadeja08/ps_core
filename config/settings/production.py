from .base import *  # noqa: F403

import os

import dj_database_url

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

REQUIRE_OTP_PROVIDER_CONFIG = env.bool("REQUIRE_OTP_PROVIDER_CONFIG", default=False)  # noqa: F405

if REQUIRE_OTP_PROVIDER_CONFIG and OTP_AUTH_PROVIDER.endswith("Msg91OtpProvider"):  # noqa: F405
    if not MSG91_AUTH_KEY:  # noqa: F405
        raise RuntimeError("MSG91_AUTH_KEY must be set in production.")
    if not MSG91_TEMPLATE_ID:  # noqa: F405
        raise RuntimeError("MSG91_TEMPLATE_ID must be set in production.")

if OTP_AUTH_PROVIDER.endswith("FirebaseAdminAuthProvider") and not (  # noqa: F405
    os.environ.get("FIREBASE_CREDENTIALS_JSON")
    or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
):
    raise RuntimeError("Firebase Admin credentials must be configured server-side in production.")
