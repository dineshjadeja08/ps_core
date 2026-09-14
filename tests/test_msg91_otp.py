from datetime import timedelta
from unittest.mock import Mock

import pytest
import requests
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException, Throttled

from apps.accounts.models import LoginOtpChallenge, OtpDeliveryChannel
from apps.accounts.otp.providers import Msg91OtpProvider
from apps.accounts.services import authenticate_with_otp


pytestmark = pytest.mark.django_db
MOBILE = "919876543210"


@pytest.fixture
def provider(settings, monkeypatch):
    settings.MSG91_AUTH_KEY = "test-only-key"
    settings.MSG91_TEMPLATE_ID = "sms-template"
    settings.MSG91_OTP_EXPIRY_MINUTES = 5
    settings.MSG91_WHATSAPP_OTP_URL = "https://api.msg91.test/whatsapp/bulk/"
    settings.MSG91_WHATSAPP_INTEGRATED_NUMBER = "911234567890"
    settings.MSG91_WHATSAPP_TEMPLATE_NAME = "login_otp"
    settings.MSG91_WHATSAPP_TEMPLATE_NAMESPACE = "template-namespace"
    settings.MSG91_WHATSAPP_TEMPLATE_LANGUAGE = "en"
    settings.OTP_AUTH_PROVIDER = "apps.accounts.otp.providers.Msg91OtpProvider"
    monkeypatch.setattr("secrets.randbelow", lambda n: 123456)
    response = Mock(status_code=200)
    response.json.return_value = {"type": "success", "request_id": "request-123"}
    post = Mock(return_value=response)
    monkeypatch.setattr("apps.accounts.otp.providers.requests.post", post)
    return Msg91OtpProvider(), post


def test_sms_send_uses_msg91_and_stores_only_hash(provider):
    otp, post = provider

    assert otp.send_otp(mobile=MOBILE, channel=OtpDeliveryChannel.SMS).request_id == "request-123"

    args = post.call_args.kwargs
    assert args["headers"]["authkey"] == "test-only-key"
    assert args["params"] == {
        "template_id": "sms-template",
        "mobile": MOBILE,
        "otp": "123456",
        "otp_expiry": 5,
    }
    challenge = LoginOtpChallenge.objects.get()
    assert challenge.code_hash != "123456"
    assert challenge.channel == OtpDeliveryChannel.SMS


def test_whatsapp_send_uses_authentication_template(provider):
    otp, post = provider

    otp.send_otp(mobile=MOBILE, channel=OtpDeliveryChannel.WHATSAPP)

    args = post.call_args.kwargs
    assert args["headers"]["authkey"] == "test-only-key"
    assert args["json"]["integrated_number"] == "911234567890"
    template = args["json"]["payload"]["template"]
    assert template["name"] == "login_otp"
    assert template["namespace"] == "template-namespace"
    components = template["to_and_components"][0]
    assert components["to"] == [MOBILE]
    assert components["components"]["body_1"]["value"] == "123456"
    assert components["components"]["button_1"]["value"] == "123456"
    assert LoginOtpChallenge.objects.get().channel == OtpDeliveryChannel.WHATSAPP


def test_code_is_consumed_once(provider):
    otp, _ = provider
    otp.send_otp(mobile=MOBILE)
    otp.verify_otp(mobile=MOBILE, otp="123456")
    with pytest.raises(serializers.ValidationError):
        otp.verify_otp(mobile=MOBILE, otp="123456")


def test_bad_attempts_persist_through_auth_service_and_lock_out(provider):
    otp, _ = provider
    otp.send_otp(mobile=MOBILE)
    for _ in range(5):
        with pytest.raises(serializers.ValidationError):
            authenticate_with_otp("+" + MOBILE, "000000")
    assert LoginOtpChallenge.objects.get().attempts == 5
    with pytest.raises(serializers.ValidationError):
        otp.verify_otp(mobile=MOBILE, otp="123456")


def test_expired_code_is_rejected(provider):
    otp, _ = provider
    otp.send_otp(mobile=MOBILE)
    LoginOtpChallenge.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    with pytest.raises(serializers.ValidationError):
        otp.verify_otp(mobile=MOBILE, otp="123456")


def test_resend_cooldown_applies_across_channels(provider):
    otp, post = provider
    otp.send_otp(mobile=MOBILE, channel=OtpDeliveryChannel.SMS)
    with pytest.raises(Throttled):
        otp.send_otp(mobile=MOBILE, channel=OtpDeliveryChannel.WHATSAPP)
    assert post.call_count == 1


def test_provider_timeout_never_leaks_secrets_or_activates_code(provider):
    otp, post = provider
    post.side_effect = requests.Timeout("test-only-key 123456")
    with pytest.raises(APIException) as error:
        otp.send_otp(mobile=MOBILE)
    assert "test-only-key" not in str(error.value)
    assert "123456" not in str(error.value)
    assert LoginOtpChallenge.objects.count() == 0


def test_provider_error_response_fails_closed(provider):
    otp, post = provider
    post.return_value.json.return_value = {"type": "error", "message": "sensitive provider diagnostic"}
    with pytest.raises(APIException):
        otp.send_otp(mobile=MOBILE)
    assert LoginOtpChallenge.objects.count() == 0


def test_unknown_provider_response_fails_closed(provider):
    otp, post = provider
    post.return_value.json.return_value = {}
    with pytest.raises(APIException):
        otp.send_otp(mobile=MOBILE)
    assert LoginOtpChallenge.objects.count() == 0


def test_missing_channel_configuration_and_non_indian_numbers(provider, settings):
    otp, post = provider
    with pytest.raises(serializers.ValidationError):
        otp.send_otp(mobile="14155551234")
    settings.MSG91_WHATSAPP_TEMPLATE_NAME = ""
    with pytest.raises(APIException):
        otp.send_otp(mobile=MOBILE, channel=OtpDeliveryChannel.WHATSAPP)
    post.assert_not_called()
