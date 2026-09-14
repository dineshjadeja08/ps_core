from django.db import models
from django.db.models import Q

from apps.bookings.models import Booking
from common.models import BaseModel


class PaymentProvider(models.TextChoices):
    RAZORPAY = "RAZORPAY", "Razorpay"
    OFFLINE = "OFFLINE", "Offline"


class PaymentType(models.TextChoices):
    BOOKING_ADVANCE = "BOOKING_ADVANCE", "Booking advance"
    BALANCE = "BALANCE", "Balance"
    REFUND = "REFUND", "Refund"


class PaymentRecordStatus(models.TextChoices):
    CREATED = "CREATED", "Created"
    PENDING = "PENDING", "Pending"
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"
    REFUNDED = "REFUNDED", "Refunded"


class Payment(BaseModel):
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="payments")
    provider = models.CharField(max_length=32, choices=PaymentProvider.choices, default=PaymentProvider.RAZORPAY)
    provider_order_id = models.CharField(max_length=128, unique=True, null=True, blank=True)
    provider_payment_id = models.CharField(max_length=128, unique=True, null=True, blank=True)
    provider_refund_id = models.CharField(max_length=128, unique=True, null=True, blank=True)
    parent_payment = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="refunds",
        null=True,
        blank=True,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    payment_type = models.CharField(max_length=32, choices=PaymentType.choices)
    status = models.CharField(max_length=32, choices=PaymentRecordStatus.choices, default=PaymentRecordStatus.CREATED)
    signature_verified = models.BooleanField(default=False)
    provider_payload = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=128, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["booking", "payment_type", "status"]),
            models.Index(fields=["provider_order_id"]),
            models.Index(fields=["provider_payment_id"]),
            models.Index(fields=["idempotency_key"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "payment_type"],
                condition=Q(
                    payment_type=PaymentType.BOOKING_ADVANCE,
                    status__in=[PaymentRecordStatus.CREATED, PaymentRecordStatus.PENDING, PaymentRecordStatus.SUCCESS],
                ),
                name="unique_active_booking_advance",
            ),
            models.UniqueConstraint(
                fields=["booking", "payment_type", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="unique_payment_idempotency_key",
            ),
        ]

    def __str__(self):
        return f"{self.provider} {self.payment_type} {self.amount}"


class WebhookProcessingStatus(models.TextChoices):
    PROCESSING = "PROCESSING", "Processing"
    PROCESSED = "PROCESSED", "Processed"
    FAILED = "FAILED", "Failed"


class PaymentWebhookEvent(BaseModel):
    payload_hash = models.CharField(max_length=64, unique=True)
    event = models.CharField(max_length=64, blank=True)
    status = models.CharField(
        max_length=16,
        choices=WebhookProcessingStatus.choices,
        default=WebhookProcessingStatus.PROCESSING,
    )
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["status", "created_at"])]
