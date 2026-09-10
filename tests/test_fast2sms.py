from datetime import timedelta
from unittest.mock import Mock
import pytest
import requests
from django.utils import timezone
from rest_framework.exceptions import APIException, Throttled
from rest_framework import serializers
from apps.accounts.models import LoginOtpChallenge
from apps.accounts.otp.providers import Fast2SmsOtpProvider
from apps.accounts.services import authenticate_with_otp

pytestmark = pytest.mark.django_db
MOBILE = "919876543210"

@pytest.fixture
def provider(settings, monkeypatch):
    settings.FAST2SMS_API_KEY = "test-only-key"
    settings.OTP_AUTH_PROVIDER = "apps.accounts.otp.providers.Fast2SmsOtpProvider"
    monkeypatch.setattr("secrets.randbelow", lambda n: 123456)
    response = Mock(status_code=200)
    response.json.return_value = {"return": True, "request_id": "request-123"}
    post = Mock(return_value=response)
    monkeypatch.setattr("apps.accounts.otp.providers.requests.post", post)
    return Fast2SmsOtpProvider(), post

def test_send_uses_header_auth_and_stores_only_hash(provider):
    otp, post = provider
    assert otp.send_otp(mobile=MOBILE).request_id == "request-123"
    args = post.call_args.kwargs
    assert args["headers"]["authorization"] == "test-only-key"
    assert args["json"] == {"route": "otp", "variables_values": "123456", "numbers": "9876543210"}
    assert "params" not in args
    assert LoginOtpChallenge.objects.get().code_hash != "123456"

def test_code_consumed_once(provider):
    otp, _ = provider; otp.send_otp(mobile=MOBILE)
    otp.verify_otp(mobile=MOBILE, otp="123456")
    with pytest.raises(serializers.ValidationError): otp.verify_otp(mobile=MOBILE, otp="123456")

def test_bad_attempts_persist_through_auth_service_and_lock_out(provider):
    otp, _ = provider; otp.send_otp(mobile=MOBILE)
    for _ in range(5):
        with pytest.raises(serializers.ValidationError): authenticate_with_otp("+" + MOBILE, "000000")
    assert LoginOtpChallenge.objects.get().attempts == 5
    with pytest.raises(serializers.ValidationError): otp.verify_otp(mobile=MOBILE, otp="123456")

def test_expired_code_rejected(provider):
    otp, _ = provider; otp.send_otp(mobile=MOBILE)
    LoginOtpChallenge.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    with pytest.raises(serializers.ValidationError): otp.verify_otp(mobile=MOBILE, otp="123456")

def test_resend_cooldown(provider):
    otp, post = provider; otp.send_otp(mobile=MOBILE)
    with pytest.raises(Throttled): otp.send_otp(mobile=MOBILE)
    assert post.call_count == 1

def test_provider_timeout_never_leaks_secrets_or_activates_code(provider):
    otp, post = provider; post.side_effect = requests.Timeout("test-only-key 123456")
    with pytest.raises(APIException) as error: otp.send_otp(mobile=MOBILE)
    assert "test-only-key" not in str(error.value)
    assert "123456" not in str(error.value)
    assert LoginOtpChallenge.objects.count() == 0

def test_provider_error_response_fails_closed(provider):
    otp, post = provider; post.return_value.json.return_value = {"return": False, "message": "sensitive provider diagnostic"}
    with pytest.raises(APIException): otp.send_otp(mobile=MOBILE)
    assert LoginOtpChallenge.objects.count() == 0

def test_missing_configuration_and_non_indian_numbers(provider, settings):
    otp, post = provider
    with pytest.raises(serializers.ValidationError): otp.send_otp(mobile="14155551234")
    settings.FAST2SMS_API_KEY = ""
    with pytest.raises(APIException): otp.send_otp(mobile=MOBILE)
    post.assert_not_called()
