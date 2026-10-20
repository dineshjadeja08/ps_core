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


class Msg91WhatsAppNotificationProvider(BaseNotificationProvider):
    provider_name = "msg91-whatsapp"
    timeout_seconds = 10

    def send(self, notification):
        if notification.channel != "WHATSAPP":
            raise ValueError("MSG91 WhatsApp provider only supports WhatsApp notifications.")
        if not notification.recipient or not notification.recipient.phone_number:
            raise ValueError("Notification recipient does not have a mobile number.")
        template_name = getattr(
            settings,
            f"MSG91_WHATSAPP_TEMPLATE_{notification.event}",
            "",
        ) or settings.MSG91_WHATSAPP_NOTIFICATION_TEMPLATE_NAME
        if not all(
            (
                settings.MSG91_AUTH_KEY,
                settings.MSG91_WHATSAPP_INTEGRATED_NUMBER,
                settings.MSG91_WHATSAPP_TEMPLATE_NAMESPACE,
                template_name,
            )
        ):
            raise ValueError("MSG91 WhatsApp notifications are not fully configured.")

        booking = notification.booking
        schedule = ""
        service_name = ""
        booking_number = ""
        if booking:
            booking_number = booking.booking_number
            service_name = booking.service.name
            schedule = f"{booking.service_date.isoformat()} {booking.time_slot.start_time.strftime('%H:%M')}"
        mobile = notification.recipient.phone_number.replace("+", "")
        body_values = [booking_number or "Purple Squad", service_name or "Service update", schedule or "Not scheduled", notification.message]
        components = {
            f"body_{index}": {"type": "text", "value": value}
            for index, value in enumerate(body_values, start=1)
        }
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
                "CRQID": str(notification.id),
                "payload": {
                    "messaging_product": "whatsapp",
                    "type": "template",
                    "template": {
                        "name": template_name,
                        "language": {
                            "code": settings.MSG91_WHATSAPP_TEMPLATE_LANGUAGE,
                            "policy": "deterministic",
                        },
                        "namespace": settings.MSG91_WHATSAPP_TEMPLATE_NAMESPACE,
                        "to_and_components": [{"to": [mobile], "components": components}],
                    },
                },
            },
            timeout=self.timeout_seconds,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("MSG91 returned an invalid response.") from exc
        if response.status_code >= 400 or not isinstance(payload, dict):
            raise ValueError("MSG91 rejected the WhatsApp notification.")
        status = str(payload.get("status", payload.get("type", ""))).lower()
        message_id = payload.get("request_id") or payload.get("message_id") or payload.get("requestId")
        if status in {"error", "failed", "failure"} or not (message_id or status in {"success", "sent", "accepted"}):
            raise ValueError("MSG91 rejected the WhatsApp notification.")
        return NotificationDeliveryResult(provider=self.provider_name, provider_message_id=str(message_id or notification.id))


class ExpoPushProvider(BaseNotificationProvider):
    """Sends PUSH notifications to every active Expo push token of the recipient."""

    provider_name = "expo-push"
    timeout_seconds = 10

    def send(self, notification):
        from apps.notifications.models import PushDevice

        devices = list(PushDevice.objects.filter(user=notification.recipient, is_active=True)) if notification.recipient else []
        if not devices:
            return NotificationDeliveryResult(provider=self.provider_name, provider_message_id="no-devices")
        data = {"event": notification.event, **(notification.payload or {})}
        if notification.booking_id:
            data["booking_id"] = str(notification.booking_id)
        messages = [
            {"to": device.token, "title": notification.title, "body": notification.message, "data": data, "sound": "default", "priority": "high", "channelId": "jobs"}
            for device in devices
        ]
        headers = {"accept": "application/json", "content-type": "application/json"}
        if getattr(settings, "EXPO_PUSH_ACCESS_TOKEN", ""):
            headers["authorization"] = f"Bearer {settings.EXPO_PUSH_ACCESS_TOKEN}"
        response = requests.post(settings.EXPO_PUSH_URL, json=messages, headers=headers, timeout=self.timeout_seconds)
        response.raise_for_status()
        tickets = response.json().get("data", [])
        stale = [device.id for device, ticket in zip(devices, tickets) if (ticket.get("details") or {}).get("error") == "DeviceNotRegistered"]
        if stale:
            PushDevice.objects.filter(id__in=stale).update(is_active=False)
        ids = [ticket.get("id", "") for ticket in tickets if ticket.get("status") == "ok"]
        if not ids:
            raise ValueError(f"Expo rejected every push message: {tickets}")
        return NotificationDeliveryResult(provider=self.provider_name, provider_message_id=",".join(ids)[:128])
