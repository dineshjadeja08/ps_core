from .base import *  # noqa: F403

import os

DEBUG = False

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
    raise RuntimeError("DJANGO_ALLOWED_HOSTS must be set in production.")

if not DATABASES["default"].get("NAME"):  # noqa: F405
    raise RuntimeError("DATABASE_URL must be set in production.")

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

if OTP_AUTH_PROVIDER.endswith("Msg91OtpProvider"):  # noqa: F405
    if not MSG91_AUTH_KEY:  # noqa: F405
        raise RuntimeError("MSG91_AUTH_KEY must be set in production.")
    if not MSG91_TEMPLATE_ID:  # noqa: F405
        raise RuntimeError("MSG91_TEMPLATE_ID must be set in production.")

if OTP_AUTH_PROVIDER.endswith("FirebaseAdminAuthProvider") and not (  # noqa: F405
    os.environ.get("FIREBASE_CREDENTIALS_JSON")
    or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
):
    raise RuntimeError("Firebase Admin credentials must be configured server-side in production.")
