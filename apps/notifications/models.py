from django.conf import settings
from django.db import models

from apps.bookings.models import Booking
from common.models import BaseModel


class NotificationChannel(models.TextChoices):
    SMS = "SMS", "SMS"
    EMAIL = "EMAIL", "Email"
    WHATSAPP = "WHATSAPP", "WhatsApp"
    IN_APP = "IN_APP", "In-app"
    PUSH = "PUSH", "Push"


class NotificationEvent(models.TextChoices):
    BOOKING_RECEIVED = "BOOKING_RECEIVED", "Booking received"
    PAYMENT_PENDING = "PAYMENT_PENDING", "Payment pending"
    PAYMENT_SUCCESSFUL = "PAYMENT_SUCCESSFUL", "Payment successful"
    BOOKING_CONFIRMED = "BOOKING_CONFIRMED", "Booking confirmed"
    BOOKING_RESCHEDULED = "BOOKING_RESCHEDULED", "Booking rescheduled"
    TECHNICIAN_ASSIGNED = "TECHNICIAN_ASSIGNED", "Technician assigned"
    TECHNICIAN_CHANGED = "TECHNICIAN_CHANGED", "Technician changed"
    BOOKING_CANCELLED = "BOOKING_CANCELLED", "Booking cancelled"
    TECHNICIAN_EN_ROUTE = "TECHNICIAN_EN_ROUTE", "Technician en route"
    TECHNICIAN_ARRIVED = "TECHNICIAN_ARRIVED", "Technician arrived"
    SERVICE_STARTED = "SERVICE_STARTED", "Service started"
    SERVICE_COMPLETED = "SERVICE_COMPLETED", "Service completed"
    BALANCE_PAYMENT_PENDING = "BALANCE_PAYMENT_PENDING", "Balance payment pending"
    BALANCE_PAYMENT_SUCCESSFUL = "BALANCE_PAYMENT_SUCCESSFUL", "Balance payment successful"
    REFUND_INITIATED = "REFUND_INITIATED", "Refund initiated"
    REFUND_COMPLETED = "REFUND_COMPLETED", "Refund completed"
    REVIEW_REQUEST = "REVIEW_REQUEST", "Review request"


class NotificationStatus(models.TextChoices):
    QUEUED = "QUEUED", "Queued"
    SENT = "SENT", "Sent"
    FAILED = "FAILED", "Failed"
    CANCELLED = "CANCELLED", "Cancelled"


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
    send_attempts = models.PositiveIntegerField(default=0)
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
