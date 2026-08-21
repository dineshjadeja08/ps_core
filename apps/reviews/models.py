from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.bookings.models import Booking
from common.models import BaseModel


class Review(BaseModel):
    booking = models.OneToOneField(Booking, on_delete=models.PROTECT, related_name="review")
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reviews")
    technician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="technician_reviews",
        null=True,
        blank=True,
    )
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField()
    is_visible = models.BooleanField(default=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["customer", "created_at"]),
            models.Index(fields=["technician", "created_at"]),
            models.Index(fields=["is_visible", "created_at"]),
        ]

    def __str__(self):
        return f"{self.booking.booking_number}: {self.rating}"
