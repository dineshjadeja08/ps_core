import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework.test import APIRequestFactory
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


def test_restore_requires_explicit_confirmation(settings):
    settings.BACKUP_S3_ENDPOINT_URL = "https://storage.example.test"
    settings.BACKUP_S3_BUCKET = "backups"
    settings.BACKUP_S3_ACCESS_KEY_ID = "access"
    settings.BACKUP_S3_SECRET_ACCESS_KEY = "secret"
    with pytest.raises(CommandError, match="confirm-restore"):
        call_command(
            "restore_database_backup",
            backup_key="postgres/test.dump",
            target_database_url="postgresql://user:pass@localhost/restore_test",
        )


def test_restore_refuses_to_overwrite_configured_database(settings, monkeypatch):
    settings.BACKUP_S3_ENDPOINT_URL = "https://storage.example.test"
    settings.BACKUP_S3_BUCKET = "backups"
    settings.BACKUP_S3_ACCESS_KEY_ID = "access"
    settings.BACKUP_S3_SECRET_ACCESS_KEY = "secret"
    production_url = "postgresql://user:pass@localhost/production"
    monkeypatch.setenv("DATABASE_URL", production_url)
    with pytest.raises(CommandError, match="Refusing to restore"):
        call_command(
            "restore_database_backup",
            backup_key="postgres/test.dump",
            target_database_url=production_url,
            confirm_restore=True,
        )


def test_backup_command_rejects_non_postgresql_database():
    with pytest.raises(CommandError, match="require PostgreSQL"):
        call_command("backup_database")
