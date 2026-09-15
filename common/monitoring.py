import logging

import sentry_sdk
from django.conf import settings


logger = logging.getLogger("purple_squad.operations")


def report_operational_failure(category: str, message: str, *, exception=None, context=None, level="error"):
    safe_context = {str(key): str(value)[:256] for key, value in (context or {}).items()}
    getattr(logger, level, logger.error)(
        "operational_failure category=%s message=%s context=%s",
        category,
        message,
        safe_context,
        exc_info=exception is not None,
    )
    if not getattr(settings, "SENTRY_DSN", ""):
        return
    with sentry_sdk.new_scope() as scope:
        scope.set_tag("failure.category", category)
        for key, value in safe_context.items():
            scope.set_extra(key, value)
        if exception is not None:
            sentry_sdk.capture_exception(exception)
        else:
            sentry_sdk.capture_message(message, level=level)
