from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.bookings.models import Booking
from apps.catalogue.models import Service
from apps.locations.models import ServiceArea
from common.models import BaseModel


class TechnicianType(models.TextChoices):
    EMPLOYEE = "EMPLOYEE", "Employee"
    CONTRACT = "CONTRACT", "Contract technician"
    PARTNER = "PARTNER", "Service partner"


class TechnicianEmploymentStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    INACTIVE = "INACTIVE", "Inactive"
    LEFT = "LEFT", "Left"


class TechnicianVerificationStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    UNDER_REVIEW = "UNDER_REVIEW", "Under review"
    VERIFIED = "VERIFIED", "Verified"
    REJECTED = "REJECTED", "Rejected"
    SUSPENDED = "SUSPENDED", "Suspended"


class TechnicianAvailabilityStatus(models.TextChoices):
    AVAILABLE = "AVAILABLE", "Available"
    BUSY = "BUSY", "Busy"
    ON_LEAVE = "ON_LEAVE", "On leave"
    OFFLINE = "OFFLINE", "Offline"
    SUSPENDED = "SUSPENDED", "Suspended"


class Weekday(models.IntegerChoices):
    MONDAY = 0, "Monday"
    TUESDAY = 1, "Tuesday"
    WEDNESDAY = 2, "Wednesday"
    THURSDAY = 3, "Thursday"
    FRIDAY = 4, "Friday"
    SATURDAY = 5, "Saturday"
    SUNDAY = 6, "Sunday"


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
    profile_photo = models.ImageField(upload_to="technicians/photos/", blank=True)
    phone = models.CharField(max_length=16)
    alternate_phone = models.CharField(max_length=16, blank=True)
    email = models.EmailField(blank=True)
    technician_type = models.CharField(
        max_length=24,
        choices=TechnicianType.choices,
        default=TechnicianType.EMPLOYEE,
    )
    employment_status = models.CharField(
        max_length=24,
        choices=TechnicianEmploymentStatus.choices,
        default=TechnicianEmploymentStatus.ACTIVE,
    )
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    pincode = models.CharField(max_length=20, blank=True)
    skills = models.ManyToManyField(TechnicianSkill, blank=True, related_name="technicians")
    service_areas = models.ManyToManyField(ServiceArea, blank=True, related_name="technicians")
    supported_services = models.ManyToManyField(Service, blank=True, related_name="technicians")
    experience_years = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    languages = models.JSONField(default=list, blank=True)
    id_proof_type = models.CharField(max_length=80, blank=True)
    id_proof_number = models.CharField(max_length=120, blank=True)
    id_proof_document = models.FileField(upload_to="technicians/id-proofs/", blank=True)
    address_proof_document = models.FileField(upload_to="technicians/address-proofs/", blank=True)
    background_verification_status = models.CharField(
        max_length=24,
        choices=TechnicianVerificationStatus.choices,
        default=TechnicianVerificationStatus.PENDING,
    )
    availability_status = models.CharField(
        max_length=24,
        choices=TechnicianAvailabilityStatus.choices,
        default=TechnicianAvailabilityStatus.AVAILABLE,
    )
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    completed_job_count = models.PositiveIntegerField(default=0)
    cancellation_count = models.PositiveIntegerField(default=0)
    is_available = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateField(null=True, blank=True)
    internal_notes = models.TextField(blank=True)

    class Meta:
        ordering = ("display_name",)
        indexes = [
            models.Index(fields=["employee_code"]),
            models.Index(fields=["phone"]),
            models.Index(fields=["city", "pincode"]),
            models.Index(fields=["background_verification_status", "availability_status"]),
            models.Index(fields=["is_active", "is_available"]),
        ]

    def __str__(self):
        return f"{self.display_name} ({self.employee_code})"

    @property
    def is_verified(self):
        return self.background_verification_status == TechnicianVerificationStatus.VERIFIED

    def clean(self):
        errors = {}
        if self.experience_years is not None and self.experience_years < 0:
            errors["experience_years"] = "Experience cannot be negative."
        if self.average_rating is not None and not (0 <= self.average_rating <= 5):
            errors["average_rating"] = "Average rating must be between 0 and 5."
        if self.availability_status == TechnicianAvailabilityStatus.SUSPENDED and self.is_active:
            errors["availability_status"] = "Suspended technicians must be inactive."
        if self.background_verification_status == TechnicianVerificationStatus.SUSPENDED and self.is_active:
            errors["background_verification_status"] = "Suspended technicians must be inactive."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.availability_status in {TechnicianAvailabilityStatus.ON_LEAVE, TechnicianAvailabilityStatus.SUSPENDED}:
            self.is_available = False
        self.full_clean()
        return super().save(*args, **kwargs)


class TechnicianWorkingHours(BaseModel):
    technician = models.ForeignKey(TechnicianProfile, on_delete=models.CASCADE, related_name="working_hours")
    day_of_week = models.PositiveSmallIntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("technician", "day_of_week", "start_time")
        constraints = [
            models.UniqueConstraint(
                fields=["technician", "day_of_week", "start_time", "end_time"],
                name="unique_technician_working_window",
            ),
        ]

    def __str__(self):
        return f"{self.technician} {self.get_day_of_week_display()} {self.start_time}-{self.end_time}"

    def clean(self):
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({"end_time": "End time must be after start time."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class TechnicianLeave(BaseModel):
    technician = models.ForeignKey(TechnicianProfile, on_delete=models.CASCADE, related_name="leaves")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    reason = models.CharField(max_length=160)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="technician_leaves_approved",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-start_at",)
        indexes = [
            models.Index(fields=["technician", "is_active", "start_at", "end_at"]),
        ]

    def __str__(self):
        return f"{self.technician} leave {self.start_at} - {self.end_at}"

    def clean(self):
        if self.start_at and self.end_at and self.start_at >= self.end_at:
            raise ValidationError({"end_at": "End time must be after start time."})

    def overlaps(self, start_at, end_at):
        return self.is_active and self.start_at < end_at and self.end_at > start_at

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class TechnicianAssignment(BaseModel):
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="technician_assignments")
    technician = models.ForeignKey(TechnicianProfile, on_delete=models.PROTECT, related_name="assignments")
    previous_technician = models.ForeignKey(
        TechnicianProfile,
        on_delete=models.PROTECT,
        related_name="previous_assignments",
        null=True,
        blank=True,
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="technician_assignments_made",
        null=True,
        blank=True,
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    unassigned_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=160, blank=True)
    notification_status = models.CharField(max_length=32, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-assigned_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["booking"],
                condition=models.Q(unassigned_at__isnull=True),
                name="unique_active_assignment_per_booking",
            ),
        ]
        indexes = [
            models.Index(fields=["booking", "assigned_at"]),
            models.Index(fields=["technician", "unassigned_at"]),
        ]

    def __str__(self):
        return f"{self.booking.booking_number} -> {self.technician.display_name}"

    @property
    def is_active_assignment(self):
        return self.unassigned_at is None

    def clean(self):
        if self.unassigned_at and self.unassigned_at < self.assigned_at:
            raise ValidationError({"unassigned_at": "Unassigned time cannot be before assignment time."})

    def save(self, *args, **kwargs):
        if self.unassigned_at is None:
            self.full_clean()
        return super().save(*args, **kwargs)
