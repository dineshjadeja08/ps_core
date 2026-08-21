from django.db import transaction

from apps.audit.models import AuditLog


SENSITIVE_KEYS = {
    "authorization",
    "password",
    "refresh",
    "token",
    "id_token",
    "signature",
    "razorpay_signature",
    "secret",
    "key_secret",
}


def audit_event(*, action, resource_type, resource_id="", actor=None, request=None, metadata=None):
    data = redact_mapping(metadata or {})

    def _write():
        AuditLog.objects.create(
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id or ""),
            request_id=getattr(request, "request_id", "") if request is not None else "",
            ip_address=get_client_ip(request),
            user_agent=(request.META.get("HTTP_USER_AGENT", "")[:1000] if request is not None else ""),
            metadata=data,
        )

    transaction.on_commit(_write)


def redact_mapping(value):
    if isinstance(value, dict):
        return {
            key: "***" if key.lower() in SENSITIVE_KEYS else redact_mapping(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_mapping(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def get_client_ip(request):
    if request is None:
        return None
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
