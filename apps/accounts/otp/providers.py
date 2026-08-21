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
