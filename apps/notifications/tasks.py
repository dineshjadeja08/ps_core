from django.db import transaction

from apps.notifications.models import Notification, NotificationStatus
from apps.notifications.services import send_notification


def deliver_notification(notification_id):
    """Deliver a notification synchronously until background jobs are restored."""
    with transaction.atomic():
        notification = (
            Notification.objects.select_for_update()
            .select_related("recipient", "booking__service", "booking__time_slot")
            .get(id=notification_id)
        )
        if notification.status in {
            NotificationStatus.SENT,
            NotificationStatus.DELIVERED,
            NotificationStatus.READ,
            NotificationStatus.CANCELLED,
        }:
            return notification.status
        send_notification(notification, raise_on_failure=True)
        return notification.status
