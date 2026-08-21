from django.conf import settings
from django.db import models

from apps.catalogue.models import Service
from apps.locations.models import Address
from apps.scheduling.models import TimeSlot
from common.models import BaseModel


class BookingStatus(models.TextChoices):
    PENDING_PAYMENT = "PENDING_PAYMENT", "Pending payment"
    PAYMENT_FAILED = "PAYMENT_FAILED", "Payment failed"
    CONFIRMED = "CONFIRMED", "Confirmed"
    TECHNICIAN_ASSIGNED = "TECHNICIAN_ASSIGNED", "Technician assigned"
    TECHNICIAN_EN_ROUTE = "TECHNICIAN_EN_ROUTE", "Technician en route"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"
    REFUND_PENDING = "REFUND_PENDING", "Refund pending"
    REFUNDED = "REFUNDED", "Refunded"


class PaymentStatus(models.TextChoices):
    UNPAID = "UNPAID", "Unpaid"
    PARTIALLY_PAID = "PARTIALLY_PAID", "Partially paid"
    PAID = "PAID", "Paid"
    FAILED = "FAILED", "Failed"
    REFUNDED = "REFUNDED", "Refunded"


class Booking(BaseModel):
    booking_number = models.CharField(max_length=32, unique=True)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bookings")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="bookings")
    address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name="bookings")
    address_snapshot = models.JSONField()
    service_date = models.DateField()
    time_slot = models.ForeignKey(TimeSlot, on_delete=models.PROTECT, related_name="bookings")
    problem_description = models.TextField()
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    advance_required = models.DecimalField(max_digits=10, decimal_places=2)
    advance_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance_due = models.DecimalField(max_digits=10, decimal_places=2)
    balance_collected = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    booking_status = models.CharField(
        max_length=32,
        choices=BookingStatus.choices,
        default=BookingStatus.PENDING_PAYMENT,
    )
    payment_status = models.CharField(max_length=32, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)
    assigned_technician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assigned_bookings",
        null=True,
        blank=True,
    )
    customer_notes = models.TextField(blank=True)
    admin_notes = models.TextField(blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["booking_number"]),
            models.Index(fields=["booking_status"]),
            models.Index(fields=["service_date"]),
            models.Index(fields=["customer"]),
            models.Index(fields=["assigned_technician"]),
            models.Index(fields=["customer", "booking_status"]),
            models.Index(fields=["time_slot", "booking_status"]),
        ]

    def __str__(self):
        return self.booking_number


class BookingStatusHistory(BaseModel):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="status_history")
    from_status = models.CharField(max_length=32, blank=True)
    to_status = models.CharField(max_length=32)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="booking_status_changes",
        null=True,
        blank=True,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("created_at",)
        verbose_name_plural = "booking status histories"
        indexes = [
            models.Index(fields=["booking", "created_at"]),
            models.Index(fields=["to_status"]),
        ]

    def __str__(self):
        return f"{self.booking.booking_number}: {self.from_status} -> {self.to_status}"
