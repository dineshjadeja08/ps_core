import requests
from django.conf import settings
from rest_framework import serializers


TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def verify_turnstile(*, token, remote_ip="", expected_action="otp_send"):
    if not settings.REQUIRE_TURNSTILE_FOR_OTP:
        return
    if not token:
        raise serializers.ValidationError({"captcha_token": "Complete the security check before requesting an OTP."})
    try:
        response = requests.post(
            TURNSTILE_VERIFY_URL,
            data={"secret": settings.TURNSTILE_SECRET_KEY, "response": token, "remoteip": remote_ip},
            timeout=8,
        )
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise serializers.ValidationError({"captcha_token": "Security verification is temporarily unavailable."}) from exc
    if response.status_code >= 400 or not result.get("success") or result.get("action") not in {None, "", expected_action}:
        raise serializers.ValidationError({"captcha_token": "Security verification failed. Please try again."})
