from unittest.mock import Mock
from django.core.cache import cache
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.request import Request
from rest_framework.parsers import JSONParser

from apps.accounts.views import OtpSendView, OtpVerifyView, PasswordLoginView
from apps.payments.views import BookingAdvancePaymentOrderView, PaymentVerifyView
from common.throttles import (
    LoginIPThrottle,
    LoginPhoneThrottle,
    OtpSendIPThrottle,
    OtpSendPhoneThrottle,
    OtpVerifyIPThrottle,
    OtpVerifyPhoneThrottle,
    PaymentIPThrottle,
    PaymentUserThrottle,
)


def configured(throttle_class, rate):
    throttle = throttle_class()
    throttle.rate = rate
    throttle.num_requests, throttle.duration = throttle.parse_rate(rate)
    return throttle


def drf_request(request):
    return Request(request, parsers=[JSONParser()])


def test_sensitive_endpoints_have_dedicated_phone_ip_and_user_throttles():
    assert PasswordLoginView.throttle_classes == [LoginIPThrottle, LoginPhoneThrottle]
    assert OtpSendView.throttle_classes == [OtpSendIPThrottle, OtpSendPhoneThrottle]
    assert OtpVerifyView.throttle_classes == [OtpVerifyIPThrottle, OtpVerifyPhoneThrottle]
    assert BookingAdvancePaymentOrderView.throttle_classes == [PaymentUserThrottle, PaymentIPThrottle]
    assert PaymentVerifyView.throttle_classes == [PaymentUserThrottle, PaymentIPThrottle]


def test_otp_phone_limit_applies_across_different_ip_addresses():
    cache.clear()
    factory = APIRequestFactory()
    first = drf_request(factory.post("/", {"phone_number": "+919876543210"}, format="json", REMOTE_ADDR="192.0.2.1"))
    second = drf_request(factory.post("/", {"phone_number": "+919876543210"}, format="json", REMOTE_ADDR="192.0.2.2"))

    assert configured(OtpSendPhoneThrottle, "1/hour").allow_request(first, None) is True
    assert configured(OtpSendPhoneThrottle, "1/hour").allow_request(second, None) is False


def test_otp_ip_limit_applies_across_different_phone_numbers():
    cache.clear()
    factory = APIRequestFactory()
    first = drf_request(factory.post("/", {"phone_number": "+919876543210"}, format="json", REMOTE_ADDR="192.0.2.5"))
    second = drf_request(factory.post("/", {"phone_number": "+919876543211"}, format="json", REMOTE_ADDR="192.0.2.5"))

    assert configured(OtpSendIPThrottle, "1/hour").allow_request(first, None) is True
    assert configured(OtpSendIPThrottle, "1/hour").allow_request(second, None) is False


def test_otp_send_requires_turnstile_when_enabled(settings):
    settings.REQUIRE_TURNSTILE_FOR_OTP = True
    settings.TURNSTILE_SECRET_KEY = "turnstile-secret"

    response = APIClient().post(
        "/api/v1/auth/otp/send/",
        {"phone_number": "+919876543210", "channel": "SMS"},
        format="json",
    )

    assert response.status_code == 400


def test_otp_send_accepts_valid_turnstile(settings, monkeypatch):
    settings.REQUIRE_TURNSTILE_FOR_OTP = True
    settings.TURNSTILE_SECRET_KEY = "turnstile-secret"
    verification = Mock(status_code=200)
    verification.json.return_value = {"success": True, "action": "otp_send"}
    monkeypatch.setattr("common.turnstile.requests.post", Mock(return_value=verification))
    monkeypatch.setattr(
        "apps.accounts.views.send_login_otp",
        Mock(return_value={"phone_number": "+919876543210", "request_id": "otp-1", "channel": "SMS"}),
    )

    response = APIClient().post(
        "/api/v1/auth/otp/send/",
        {"phone_number": "+919876543210", "channel": "SMS", "captcha_token": "valid-token"},
        format="json",
    )

    assert response.status_code == 200
