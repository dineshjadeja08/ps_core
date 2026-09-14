import hashlib
import json
import re

from rest_framework import serializers


IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


def idempotency_key_from_request(request, *, fallback: str = "") -> str:
    key = request.headers.get("Idempotency-Key", "").strip() or fallback
    if not IDEMPOTENCY_KEY_PATTERN.fullmatch(key):
        raise serializers.ValidationError(
            {"idempotency_key": "Idempotency-Key must contain 8 to 128 letters, numbers, dots, colons, underscores, or hyphens."}
        )
    return key


def request_fingerprint(payload) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
