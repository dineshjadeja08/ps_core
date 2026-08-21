import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from apps.notifications.models import Notification, NotificationChannel, NotificationEvent, NotificationStatus


logger = logging.getLogger(__name__)


DEFAULT_CHANNELS = (NotificationChannel.PUSH,)


def emit_notification_event(*, event, recipient, booking=None, channels=None, payload=None):
    channels = channels or DEFAULT_CHANNELS
    payload = payload or {}

    def _create_and_send():
        for channel in channels:
            try:
                notification = Notification.objects.create(
                    recipient=recipient,
                    booking=booking,
                    event=event,
                    channel=channel,
                    title=_title_for_event(event),
                    message=_message_for_event(event, booking),
                    payload=payload,
                )
                send_notification(notification)
            except Exception:
                logger.exception("notification_event_failed event=%s channel=%s", event, channel)

    transaction.on_commit(_create_and_send)


def send_notification(notification):
    provider = get_notification_provider()
    try:
        result = provider.send(notification)
    except Exception as exc:
        notification.status = NotificationStatus.FAILED
        notification.provider = getattr(provider, "provider_name", "")
        notification.error_message = str(exc)
        notification.save(update_fields=["status", "provider", "error_message", "updated_at"])
        logger.exception("notification_send_failed notification_id=%s", notification.id)
        return notification

    notification.status = NotificationStatus.SENT
    notification.provider = result.provider
    notification.provider_message_id = result.provider_message_id
    notification.sent_at = timezone.now()
    notification.save(update_fields=["status", "provider", "provider_message_id", "sent_at", "updated_at"])
    return notification


def get_notification_provider():
    provider_path = getattr(settings, "NOTIFICATION_PROVIDER", "apps.notifications.providers.LocalNotificationProvider")
    return import_string(provider_path)()


def _title_for_event(event):
    titles = {
        NotificationEvent.BOOKING_CONFIRMED: "Booking confirmed",
        NotificationEvent.TECHNICIAN_ASSIGNED: "Technician assigned",
        NotificationEvent.BOOKING_CANCELLED: "Booking cancelled",
        NotificationEvent.SERVICE_COMPLETED: "Service completed",
    }
    return titles.get(event, "Purple Squad update")


def _message_for_event(event, booking):
    booking_number = booking.booking_number if booking else "your booking"
    messages = {
        NotificationEvent.BOOKING_CONFIRMED: f"{booking_number} is confirmed.",
        NotificationEvent.TECHNICIAN_ASSIGNED: f"A technician has been assigned to {booking_number}.",
        NotificationEvent.BOOKING_CANCELLED: f"{booking_number} has been cancelled.",
        NotificationEvent.SERVICE_COMPLETED: f"{booking_number} has been completed.",
    }
    return messages.get(event, f"Update for {booking_number}.")
