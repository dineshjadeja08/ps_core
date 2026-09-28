from firebase_admin import messaging

from apps.notifications.models import DeviceToken
from common.firebase import get_firebase_app


class FcmDeliveryResult:
    provider = "firebase-fcm"

    def __init__(self, provider_message_id=""):
        self.provider_message_id = provider_message_id


def send(notification):
    """Send one FCM message to every active device registered by the recipient."""
    if notification.channel != "PUSH":
        raise ValueError("Firebase Cloud Messaging only supports push notifications.")
    if not notification.recipient_id:
        raise ValueError("Push notification has no recipient.")

    tokens = list(DeviceToken.objects.filter(user_id=notification.recipient_id, is_active=True))
    if not tokens:
        raise ValueError("Notification recipient has no active FCM device token.")

    app = get_firebase_app()
    data = {str(key): str(value) for key, value in notification.payload.items() if value is not None}
    data.update({"event": notification.event, "notification_id": str(notification.id)})
    if notification.booking_id:
        data["booking_id"] = str(notification.booking_id)
        data["route"] = f"/bookings/{notification.booking_id}"

    message_ids = []
    failures = []
    for device in tokens:
        message = messaging.Message(
            notification=messaging.Notification(title=notification.title, body=notification.message),
            data=data,
            token=device.token,
            webpush=messaging.WebpushConfig(
                fcm_options=messaging.WebpushFCMOptions(link=data.get("route", "/bookings")),
            ),
        )
        try:
            message_ids.append(messaging.send(message, app=app))
        except (messaging.UnregisteredError, messaging.SenderIdMismatchError):
            device.is_active = False
            device.save(update_fields=["is_active", "updated_at"])
        except Exception as exc:
            failures.append(str(exc))

    if not message_ids:
        raise ValueError(f"FCM delivery failed for every registered device: {'; '.join(failures)[:500]}")
    return FcmDeliveryResult(",".join(message_ids)[:128])


class FirebaseCloudMessagingProvider:
    provider_name = "firebase-fcm"

    def send(self, notification):
        return send(notification)
