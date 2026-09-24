import hashlib

from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle, UserRateThrottle


def _opaque_identifier(value: object) -> str:
    normalized = "".join(character for character in str(value or "").lower() if character.isalnum() or character in "-_")
    if not normalized:
        return "missing"
    return hashlib.sha256(f"{settings.SECRET_KEY}:{normalized}".encode("utf-8")).hexdigest()


class ClientIPThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class RequestIdentifierThrottle(SimpleRateThrottle):
    request_field = "phone_number"

    def get_cache_key(self, request, view):
        value = request.data.get(self.request_field) if isinstance(request.data, dict) else None
        return self.cache_format % {"scope": self.scope, "ident": _opaque_identifier(value)}


class LoginIPThrottle(ClientIPThrottle):
    scope = "login_ip"


class LoginPhoneThrottle(RequestIdentifierThrottle):
    scope = "login_phone"


class OtpSendIPThrottle(ClientIPThrottle):
    scope = "otp_send_ip"


class OtpSendPhoneThrottle(RequestIdentifierThrottle):
    scope = "otp_send_phone"


class OtpVerifyIPThrottle(ClientIPThrottle):
    scope = "otp_verify_ip"


class OtpVerifyPhoneThrottle(RequestIdentifierThrottle):
    scope = "otp_verify_phone"


class MfaChallengeThrottle(OtpVerifyPhoneThrottle):
    request_field = "challenge_id"


class PaymentIPThrottle(ClientIPThrottle):
    scope = "payment_ip"


class PaymentUserThrottle(UserRateThrottle):
    scope = "payment_user"


class LocationIPThrottle(ClientIPThrottle):
    scope = "location_ip"
