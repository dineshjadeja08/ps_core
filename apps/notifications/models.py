from django.conf import settings
from django.db import models

from apps.bookings.models import Booking
from common.models import BaseModel


class NotificationChannel(models.TextChoices):
    SMS = "SMS", "SMS"
    EMAIL = "EMAIL", "Email"
    WHATSAPP = "WHATSAPP", "WhatsApp"
    PUSH = "PUSH", "Push"


class NotificationEvent(models.TextChoices):
    BOOKING_CONFIRMED = "BOOKING_CONFIRMED", "Booking confirmed"
    TECHNICIAN_ASSIGNED = "TECHNICIAN_ASSIGNED", "Technician assigned"
    BOOKING_CANCELLED = "BOOKING_CANCELLED", "Booking cancelled"
    SERVICE_COMPLETED = "SERVICE_COMPLETED", "Service completed"


class NotificationStatus(models.TextChoices):
    QUEUED = "QUEUED", "Queued"
    SENT = "SENT", "Sent"
    FAILED = "FAILED", "Failed"


class Notification(BaseModel):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="notifications",
        null=True,
        blank=True,
    )
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, related_name="notifications", null=True, blank=True)
    event = models.CharField(max_length=32, choices=NotificationEvent.choices)
    channel = models.CharField(max_length=16, choices=NotificationChannel.choices)
    status = models.CharField(max_length=16, choices=NotificationStatus.choices, default=NotificationStatus.QUEUED)
    title = models.CharField(max_length=160)
    message = models.TextField()
    provider = models.CharField(max_length=64, blank=True)
    provider_message_id = models.CharField(max_length=128, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["recipient", "created_at"]),
            models.Index(fields=["booking", "event"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["channel", "event"]),
        ]

    def __str__(self):
        return f"{self.event} {self.channel} {self.status}"
