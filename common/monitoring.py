import logging

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
