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
        if notification.event not in getattr(settings, "MSG91_SMS_ENABLED_EVENTS", ()):
            raise ValueError("SMS notifications are disabled for this event.")

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

        variable_1, variable_2 = _template_variables(notification)
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
                        "VAR1": variable_1,
                        "VAR2": variable_2,
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


def _template_variables(notification):
    payload = notification.payload or {}
    booking = notification.booking
    reference = booking.booking_number if booking else str(payload.get("lead_id") or notification.id)[:40]

    if notification.event == "PAYMENT_PENDING":
        return _limit_variable(payload.get("amount") or reference), str(payload.get("payment_link_url") or "")
    if notification.event in {"PAYMENT_SUCCESSFUL", "REFUND_INITIATED", "REFUND_COMPLETED"}:
        return _limit_variable(reference), _limit_variable(payload.get("amount") or "Updated")
    if notification.event in {"BOOKING_CONFIRMED", "BOOKING_RESCHEDULED"} and booking:
        schedule = booking.service_date.isoformat()
        if booking.time_slot_id:
            schedule = f"{schedule} {booking.time_slot.start_time.strftime('%H:%M')}"
        return _limit_variable(reference), _limit_variable(schedule)
    if notification.event == "TECHNICIAN_ASSIGNED" and booking and booking.assigned_technician_id:
        technician = booking.assigned_technician
        technician_name = f"{technician.first_name} {technician.last_name}".strip() or technician.phone_number
        return _limit_variable(reference), _limit_variable(technician_name)
    if booking and booking.service_id:
        return _limit_variable(reference), _limit_variable(booking.service.name)
    return _limit_variable(reference), _limit_variable(notification.title)


def _limit_variable(value):
    return str(value or "Update").strip()[:40]
