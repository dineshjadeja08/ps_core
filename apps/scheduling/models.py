from django.core.exceptions import ValidationError
from django.db import models

from apps.locations.models import ServiceArea
from common.models import BaseModel


class TimeSlot(BaseModel):
    service_area = models.ForeignKey(ServiceArea, on_delete=models.PROTECT, related_name="time_slots")
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    capacity = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("date", "start_time")
        constraints = [
            models.UniqueConstraint(
                fields=["service_area", "date", "start_time", "end_time"],
                name="unique_service_area_slot_time",
            ),
        ]
        indexes = [
            models.Index(fields=["service_area", "date", "is_active"]),
            models.Index(fields=["date", "start_time"]),
        ]

    def __str__(self):
        return f"{self.service_area} {self.date} {self.start_time}-{self.end_time}"

    def clean(self):
        errors = {}
        if self.capacity is not None and self.capacity <= 0:
            errors["capacity"] = "Capacity must be greater than zero."
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            errors["end_time"] = "End time must be after start time."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
