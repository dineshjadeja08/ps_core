from django.conf import settings
from django.db import models

from apps.bookings.models import Booking
from apps.locations.models import ServiceArea
from common.models import BaseModel


class TechnicianSkill(BaseModel):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class TechnicianProfile(BaseModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="technician_profile")
    employee_code = models.CharField(max_length=40, unique=True)
    display_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=16)
    skills = models.ManyToManyField(TechnicianSkill, blank=True, related_name="technicians")
    service_areas = models.ManyToManyField(ServiceArea, blank=True, related_name="technicians")
    is_available = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ("display_name",)
        indexes = [
            models.Index(fields=["employee_code"]),
            models.Index(fields=["is_active", "is_available"]),
        ]

    def __str__(self):
        return f"{self.display_name} ({self.employee_code})"


class TechnicianAssignment(BaseModel):
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="technician_assignments")
    technician = models.ForeignKey(TechnicianProfile, on_delete=models.PROTECT, related_name="assignments")
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="technician_assignments_made",
        null=True,
        blank=True,
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    unassigned_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-assigned_at",)
        indexes = [
            models.Index(fields=["booking", "assigned_at"]),
            models.Index(fields=["technician", "unassigned_at"]),
        ]

    def __str__(self):
        return f"{self.booking.booking_number} -> {self.technician.display_name}"
