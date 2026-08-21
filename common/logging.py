import logging
import re


SENSITIVE_PATTERNS = (
    re.compile(r"(authorization=)([^,\s]+)", re.IGNORECASE),
    re.compile(r"(token=)([^,\s]+)", re.IGNORECASE),
    re.compile(r"(signature=)([^,\s]+)", re.IGNORECASE),
    re.compile(r"(secret=)([^,\s]+)", re.IGNORECASE),
)


class RedactSensitiveLogFilter(logging.Filter):
    def filter(self, record):
        record.msg = redact_text(record.msg)
        if record.args:
            record.args = tuple(redact_text(arg) for arg in record.args)
        return True


def redact_text(value):
    if not isinstance(value, str):
        return value
    redacted = value
    for pattern in SENSITIVE_PATTERNS:
        redacted = pattern.sub(r"\1***", redacted)
    return redacted
