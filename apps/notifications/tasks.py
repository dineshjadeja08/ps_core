from celery import shared_task
from django.db import transaction

from apps.notifications.models import Notification, NotificationStatus
from apps.notifications.services import send_notification


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
    max_retries=5,
    acks_late=True,
)
def deliver_notification(self, notification_id):
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
