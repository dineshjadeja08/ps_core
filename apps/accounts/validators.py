import re

from rest_framework import serializers

E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_phone_number(phone_number: str) -> str:
    value = "".join(str(phone_number or "").split())
    if not E164_PATTERN.fullmatch(value):
        raise serializers.ValidationError("Phone number must be a verified E.164 value.")
    return value


def normalize_account_phone_number(phone_number: str) -> str:
    """Normalize Indian local numbers for staff account creation and password login."""
    value = "".join(str(phone_number or "").split())
    digits = re.sub(r"\D", "", value)

    if re.fullmatch(r"[6-9]\d{9}", digits):
        return f"+91{digits}"
    if re.fullmatch(r"91[6-9]\d{9}", digits):
        return f"+{digits}"
    return normalize_phone_number(value)
