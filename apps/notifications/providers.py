import re

import requests
from django.conf import settings


class NotificationDeliveryResult:
    def __init__(self, *, provider, provider_message_id=""):
        self.provider = provider
        self.provider_message_id = provider_message_id


class BaseNotificationProvider:
    provider_name = "base"

    def send(self, notification):
        raise NotImplementedError


class LocalNotificationProvider(BaseNotificationProvider):
    provider_name = "local"

    def send(self, notification):
        return NotificationDeliveryResult(
            provider=self.provider_name,
            provider_message_id=f"local_{notification.id}",
        )


class Msg91SmsNotificationProvider(BaseNotificationProvider):
    provider_name = "msg91-sms"
    timeout_seconds = 10

    def send(self, notification):
        if notification.channel != "SMS":
            raise ValueError("MSG91 SMS provider only supports SMS notifications.")

        phone_number = (notification.payload or {}).get("mobile")
        if not phone_number and notification.recipient:
            phone_number = notification.recipient.phone_number
        mobile = _normalise_mobile(phone_number)

        template_id = (
            getattr(settings, "MSG91_SMS_TEMPLATE_IDS", {}).get(notification.event)
            or getattr(settings, "MSG91_SMS_TEMPLATE_ID", "")
        )
        auth_key = getattr(settings, "MSG91_AUTH_KEY", "")
        if not auth_key or not template_id:
            raise ValueError("MSG91 SMS notifications are not fully configured.")

        booking_number = notification.booking.booking_number if notification.booking else "Purple Squad"
        response = requests.post(
            getattr(settings, "MSG91_SMS_FLOW_URL", "https://control.msg91.com/api/v5/flow"),
            headers={
                "accept": "application/json",
                "authkey": auth_key,
                "content-type": "application/json",
            },
            json={
                "template_id": template_id,
                "short_url": "1" if getattr(settings, "MSG91_SMS_SHORT_URL", True) else "0",
                "realTimeResponse": "1",
                "recipients": [
                    {
                        "mobiles": mobile,
                        "VAR1": notification.title,
                        "VAR2": notification.message,
                        "VAR3": booking_number,
                        "VAR4": str(notification.id),
                    }
                ],
            },
            timeout=self.timeout_seconds,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("MSG91 returned an invalid response.") from exc

        if response.status_code >= 400 or not isinstance(payload, dict):
            raise ValueError("MSG91 rejected the SMS notification.")
        result_type = str(payload.get("type", payload.get("status", ""))).lower()
        if result_type in {"error", "failed", "failure"}:
            raise ValueError("MSG91 rejected the SMS notification.")

        request_id = payload.get("request_id") or payload.get("requestId") or payload.get("message_id")
        if result_type not in {"success", "sent", "accepted"} and not request_id:
            raise ValueError("MSG91 did not accept the SMS notification.")
        return NotificationDeliveryResult(
            provider=self.provider_name,
            provider_message_id=str(request_id or notification.id)[:128],
        )


def _normalise_mobile(phone_number):
    digits = re.sub(r"\D", "", str(phone_number or ""))
    if len(digits) == 10:
        digits = f"91{digits}"
    elif len(digits) == 11 and digits.startswith("0"):
        digits = f"91{digits[1:]}"
    if len(digits) < 11 or len(digits) > 15:
        raise ValueError("Notification recipient does not have a valid mobile number.")
    return digits
