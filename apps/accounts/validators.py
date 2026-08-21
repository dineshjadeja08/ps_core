import re

from rest_framework import serializers

E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_phone_number(phone_number: str) -> str:
    value = "".join(str(phone_number or "").split())
    if not E164_PATTERN.fullmatch(value):
        raise serializers.ValidationError("Phone number must be a verified E.164 value.")
    return value
