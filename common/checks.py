from django.conf import settings
from django.core.checks import Error, Tags, Warning, register


@register(Tags.security, deploy=True)
def provider_secret_checks(app_configs, **kwargs):
    errors = []
    if not settings.DEBUG:
        if not settings.RAZORPAY_KEY_SECRET or settings.RAZORPAY_KEY_SECRET == "test_razorpay_secret":
            errors.append(
                Error(
                    "RAZORPAY_KEY_SECRET must be set to a non-test value.",
                    id="purple_squad.E001",
                )
            )
        if not settings.RAZORPAY_WEBHOOK_SECRET or settings.RAZORPAY_WEBHOOK_SECRET == "test_razorpay_webhook_secret":
            errors.append(
                Error(
                    "RAZORPAY_WEBHOOK_SECRET must be set to a non-test value.",
                    id="purple_squad.E002",
                )
            )
        if not settings.CORS_ALLOWED_ORIGINS:
            errors.append(
                Warning(
                    "CORS_ALLOWED_ORIGINS is empty; frontend origins must be configured before launch.",
                    id="purple_squad.W001",
                )
            )
    return errors
