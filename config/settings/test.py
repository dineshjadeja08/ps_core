from .base import *  # noqa: F403

SECRET_KEY = "test-secret-key-not-for-production-8a9f2c7e6b5d4a3c1f0e"
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
RAZORPAY_ADAPTER = "apps.payments.providers.LocalRazorpayAdapter"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].update(  # noqa: F405
    {
        "anon": "10000/min",
        "user": "10000/min",
        "auth": "10000/min",
        "payment": "10000/min",
        "webhook": "10000/min",
    }
)
