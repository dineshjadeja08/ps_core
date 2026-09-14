import re
import secrets
from dataclasses import dataclass
from datetime import timedelta

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from rest_framework import serializers
from rest_framework.exceptions import APIException, Throttled

from apps.accounts.models import LoginOtpChallenge, OtpDeliveryChannel


@dataclass(frozen=True)
class OtpProviderResult:
    request_id: str = ""


class Msg91OtpProvider:
    """Deliver OTPs with MSG91 and verify one-time challenges in our database."""

    timeout_seconds = 10

    @staticmethod
    def _hash(mobile: str, otp: str) -> str:
        return salted_hmac("purple-squad-login-otp", f"{mobile}:{otp}", algorithm="sha256").hexdigest()

    def send_otp(self, *, mobile: str, channel: str = OtpDeliveryChannel.SMS) -> OtpProviderResult:
        if not re.fullmatch(r"91[6-9][0-9]{9}", mobile):
            raise serializers.ValidationError("Please enter a valid Indian mobile number.")
        if channel not in OtpDeliveryChannel.values:
            raise serializers.ValidationError("Choose SMS or WhatsApp for OTP delivery.")

        self._ensure_configured(channel)

        with transaction.atomic():
            LoginOtpChallenge.objects.get_or_create(mobile=mobile)
            challenge = LoginOtpChallenge.objects.select_for_update().get(mobile=mobile)
            now = timezone.now()
            if challenge.sent_at and (now - challenge.sent_at).total_seconds() < 60:
                raise Throttled(wait=60, detail="Please wait before requesting another OTP.")

            code = f"{secrets.randbelow(1000000):06d}"
            payload = self._deliver(mobile=mobile, code=code, channel=channel)

            challenge.channel = channel
            challenge.code_hash = self._hash(mobile, code)
            challenge.expires_at = now + timedelta(minutes=settings.MSG91_OTP_EXPIRY_MINUTES)
            challenge.sent_at = now
            challenge.attempts = 0
            challenge.consumed_at = None
            challenge.save()

        return OtpProviderResult(request_id=str(payload.get("request_id") or payload.get("message_id") or ""))

    def verify_otp(self, *, mobile: str, otp: str) -> OtpProviderResult:
        valid = False
        with transaction.atomic():
            challenge = LoginOtpChallenge.objects.select_for_update().filter(mobile=mobile).first()
            now = timezone.now()
            if (
                challenge
                and challenge.expires_at
                and challenge.expires_at > now
                and not challenge.consumed_at
                and challenge.attempts < 5
            ):
                challenge.attempts += 1
                valid = constant_time_compare(challenge.code_hash, self._hash(mobile, otp))
                if valid:
                    challenge.consumed_at = now
                    challenge.code_hash = ""
                challenge.save(update_fields=["attempts", "consumed_at", "code_hash", "updated_at"])

        if not valid:
            raise serializers.ValidationError("Invalid or expired OTP. Request a new code if needed.")
        return OtpProviderResult()

    def _deliver(self, *, mobile: str, code: str, channel: str) -> dict:
        try:
            if channel == OtpDeliveryChannel.WHATSAPP:
                response = requests.post(
                    settings.MSG91_WHATSAPP_OTP_URL,
                    headers={
                        "accept": "application/json",
                        "authkey": settings.MSG91_AUTH_KEY,
                        "content-type": "application/json",
                    },
                    json={
                        "integrated_number": settings.MSG91_WHATSAPP_INTEGRATED_NUMBER,
                        "content_type": "template",
                        "payload": {
                            "messaging_product": "whatsapp",
                            "type": "template",
                            "template": {
                                "name": settings.MSG91_WHATSAPP_TEMPLATE_NAME,
                                "language": {
                                    "code": settings.MSG91_WHATSAPP_TEMPLATE_LANGUAGE,
                                    "policy": "deterministic",
                                },
                                "namespace": settings.MSG91_WHATSAPP_TEMPLATE_NAMESPACE,
                                "to_and_components": [
                                    {
                                        "to": [mobile],
                                        "components": {
                                            "body_1": {"type": "text", "value": code},
                                            "button_1": {
                                                "subtype": "url",
                                                "type": "text",
                                                "value": code,
                                            },
                                        },
                                    }
                                ],
                            },
                        },
                    },
                    timeout=self.timeout_seconds,
                )
            else:
                response = requests.post(
                    settings.MSG91_SEND_OTP_URL,
                    params={
                        "template_id": settings.MSG91_TEMPLATE_ID,
                        "mobile": mobile,
                        "otp": code,
                        "otp_expiry": settings.MSG91_OTP_EXPIRY_MINUTES,
                    },
                    headers={"accept": "application/json", "authkey": settings.MSG91_AUTH_KEY},
                    timeout=self.timeout_seconds,
                )
            payload = response.json()
        except (requests.RequestException, ValueError):
            raise APIException("OTP could not be sent. Please try again shortly.") from None

        if response.status_code >= 400 or not isinstance(payload, dict) or not self._is_success(payload):
            raise APIException("OTP could not be sent. Please try again shortly.")
        return payload

    @staticmethod
    def _is_success(payload: dict) -> bool:
        status = str(payload.get("status", "")).lower()
        response_type = str(payload.get("type", "")).lower()
        message = str(payload.get("message", "")).lower()
        return (
            status in {"success", "sent", "accepted"}
            or response_type == "success"
            or "success" in message
            or bool(payload.get("request_id") or payload.get("message_id"))
        )

    @staticmethod
    def _ensure_configured(channel: str) -> None:
        if not settings.MSG91_AUTH_KEY:
            raise APIException("OTP delivery is not configured. Please contact support.")
        if channel == OtpDeliveryChannel.SMS and not settings.MSG91_TEMPLATE_ID:
            raise APIException("SMS OTP delivery is not configured. Please contact support.")
        if channel == OtpDeliveryChannel.WHATSAPP and not all(
            (
                settings.MSG91_WHATSAPP_INTEGRATED_NUMBER,
                settings.MSG91_WHATSAPP_TEMPLATE_NAME,
                settings.MSG91_WHATSAPP_TEMPLATE_NAMESPACE,
            )
        ):
            raise APIException("WhatsApp OTP delivery is not configured. Please choose SMS or contact support.")
