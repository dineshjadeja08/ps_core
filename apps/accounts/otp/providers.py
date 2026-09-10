from dataclasses import dataclass

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from rest_framework import serializers


@dataclass(frozen=True)
class OtpProviderResult:
    request_id: str = ""


class Msg91OtpProvider:
    timeout_seconds = 10

    def send_otp(self, *, mobile: str) -> OtpProviderResult:
        self._ensure_configured()
        response = requests.post(
            settings.MSG91_SEND_OTP_URL,
            params={
                "template_id": settings.MSG91_TEMPLATE_ID,
                "mobile": mobile,
                "otp_expiry": settings.MSG91_OTP_EXPIRY_MINUTES,
            },
            headers={
                "accept": "application/json",
                "authkey": settings.MSG91_AUTH_KEY,
            },
            timeout=self.timeout_seconds,
        )
        payload = self._parse_response(response)
        self._raise_for_failure(payload, fallback="Could not send OTP.")
        return OtpProviderResult(request_id=str(payload.get("request_id", "")))

    def verify_otp(self, *, mobile: str, otp: str) -> OtpProviderResult:
        self._ensure_configured()
        response = requests.get(
            settings.MSG91_VERIFY_OTP_URL,
            params={
                "mobile": mobile,
                "otp": otp,
            },
            headers={
                "accept": "application/json",
                "authkey": settings.MSG91_AUTH_KEY,
            },
            timeout=self.timeout_seconds,
        )
        payload = self._parse_response(response)
        self._raise_for_failure(payload, fallback="Invalid or expired OTP.")
        return OtpProviderResult(request_id=str(payload.get("request_id", "")))

    def _ensure_configured(self):
        if not settings.MSG91_AUTH_KEY:
            raise ImproperlyConfigured("MSG91_AUTH_KEY is required.")
        if not settings.MSG91_TEMPLATE_ID:
            raise ImproperlyConfigured("MSG91_TEMPLATE_ID is required.")

    def _parse_response(self, response):
        try:
            payload = response.json()
        except ValueError as exc:
            raise serializers.ValidationError("OTP provider returned an invalid response.") from exc

        if response.status_code >= 400:
            self._raise_for_failure(payload, fallback="OTP provider request failed.")

        return payload

    def _raise_for_failure(self, payload, *, fallback: str):
        response_type = str(payload.get("type", "")).lower()
        message = str(payload.get("message", "")).lower()
        if response_type == "success" or "success" in message or "verified" in message:
            return
        raise serializers.ValidationError(fallback)


class Fast2SmsOtpProvider:
    """Fast2SMS delivers the code; expiry, attempt limits and consumption live in our DB."""
    timeout_seconds = 10

    @staticmethod
    def _hash(mobile, otp):
        from django.utils.crypto import salted_hmac
        return salted_hmac("purple-squad-login-otp", f"{mobile}:{otp}", algorithm="sha256").hexdigest()

    def send_otp(self, *, mobile):
        import re
        import secrets
        from datetime import timedelta
        from django.db import transaction
        from django.utils import timezone
        from rest_framework.exceptions import APIException, Throttled
        from apps.accounts.models import LoginOtpChallenge

        if not settings.FAST2SMS_API_KEY:
            raise APIException("OTP delivery is not configured. Please contact support.")
        if not re.fullmatch(r"91[6-9][0-9]{9}", mobile):
            raise serializers.ValidationError("Please enter a valid Indian mobile number.")
        with transaction.atomic():
            LoginOtpChallenge.objects.get_or_create(mobile=mobile)
            challenge = LoginOtpChallenge.objects.select_for_update().get(mobile=mobile)
            now = timezone.now()
            if challenge.sent_at and (now - challenge.sent_at).total_seconds() < 60:
                raise Throttled(wait=60, detail="Please wait before requesting another OTP.")
            code = f"{secrets.randbelow(1000000):06d}"
            try:
                response = requests.post(
                    "https://www.fast2sms.com/dev/bulkV2",
                    headers={"authorization": settings.FAST2SMS_API_KEY, "accept": "application/json"},
                    json={"route": "otp", "variables_values": code, "numbers": mobile[2:]},
                    timeout=self.timeout_seconds,
                )
                payload = response.json()
                if response.status_code >= 400 or not isinstance(payload, dict) or payload.get("return") is not True:
                    raise ValueError("Provider rejected delivery")
            except (requests.RequestException, ValueError):
                raise APIException("OTP could not be sent. Please try again shortly.") from None
            challenge.code_hash = self._hash(mobile, code)
            challenge.expires_at = now + timedelta(seconds=settings.FAST2SMS_OTP_TTL_SECONDS)
            challenge.sent_at = now
            challenge.attempts = 0
            challenge.consumed_at = None
            challenge.save()
            return OtpProviderResult(request_id=str(payload.get("request_id", "")))

    def verify_otp(self, *, mobile, otp):
        from django.db import transaction
        from django.utils import timezone
        from django.utils.crypto import constant_time_compare
        from apps.accounts.models import LoginOtpChallenge

        valid = False
        with transaction.atomic():
            challenge = LoginOtpChallenge.objects.select_for_update().filter(mobile=mobile).first()
            now = timezone.now()
            if (challenge and challenge.expires_at and challenge.expires_at > now
                    and not challenge.consumed_at and challenge.attempts < 5):
                challenge.attempts += 1
                valid = constant_time_compare(challenge.code_hash, self._hash(mobile, otp))
                if valid:
                    challenge.consumed_at = now
                    challenge.code_hash = ""
                challenge.save(update_fields=["attempts", "consumed_at", "code_hash", "updated_at"])
        # Raise outside the transaction so failed attempts remain recorded.
        if not valid:
            raise serializers.ValidationError("Invalid or expired OTP. Request a new code if needed.")
        return OtpProviderResult()
