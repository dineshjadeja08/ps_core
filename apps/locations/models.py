from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from common.models import BaseModel


class ServiceArea(BaseModel):
    name = models.CharField(max_length=150)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default="India")
    postal_code = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("city", "postal_code", "name")
        constraints = [
            models.UniqueConstraint(fields=["country", "postal_code"], name="unique_service_area_postal_code"),
        ]
        indexes = [
            models.Index(fields=["postal_code"]),
            models.Index(fields=["is_active", "postal_code"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.postal_code})"

    def clean(self):
        if self.postal_code:
            self.postal_code = normalize_postal_code(self.postal_code)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class Address(BaseModel):
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="addresses")
    label = models.CharField(max_length=80)
    recipient_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=16)
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True)
    landmark = models.CharField(max_length=150, blank=True)
    locality = models.CharField(max_length=150, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100, default="India")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-is_default", "-created_at")
        indexes = [
            models.Index(fields=["customer", "is_active"]),
            models.Index(fields=["postal_code"]),
            models.Index(fields=["customer", "is_default"]),
        ]

    def __str__(self):
        return f"{self.label} - {self.recipient_name}"

    def clean(self):
        errors = {}
        if self.postal_code:
            self.postal_code = normalize_postal_code(self.postal_code)
        if self.latitude is not None and not (-90 <= self.latitude <= 90):
            errors["latitude"] = "Latitude must be between -90 and 90."
        if self.longitude is not None and not (-180 <= self.longitude <= 180):
            errors["longitude"] = "Longitude must be between -180 and 180."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


def normalize_postal_code(postal_code):
    return "".join(str(postal_code or "").split()).upper()
