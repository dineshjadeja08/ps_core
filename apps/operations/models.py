from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.bookings.models import Booking
from apps.catalogue.models import Service, ServiceCategory
from common.models import BaseModel


class LeadSource(models.TextChoices):
    PHONE = "PHONE", "Phone"
    WHATSAPP = "WHATSAPP", "WhatsApp"
    WEBSITE = "WEBSITE", "Website"
    CALLBACK_REQUEST = "CALLBACK_REQUEST", "Callback request"
    ABANDONED_BOOKING = "ABANDONED_BOOKING", "Abandoned booking"
    PAYMENT_PENDING = "PAYMENT_PENDING", "Payment pending"
    MANUAL = "MANUAL", "Manual"
    OTHER = "OTHER", "Other"


class LeadStatus(models.TextChoices):
    NEW = "NEW", "New"
    CONTACTED = "CONTACTED", "Contacted"
    INTERESTED = "INTERESTED", "Interested"
    FOLLOW_UP = "FOLLOW_UP", "Follow-up"
    CONVERTED = "CONVERTED", "Converted"
    LOST = "LOST", "Lost"
    CLOSED = "CLOSED", "Closed"


ACTIVE_LEAD_STATUSES = {
    LeadStatus.NEW,
    LeadStatus.CONTACTED,
    LeadStatus.INTERESTED,
    LeadStatus.FOLLOW_UP,
}


class Lead(BaseModel):
    customer_name = models.CharField(max_length=255)
    primary_mobile = models.CharField(max_length=16)
    alternate_mobile = models.CharField(max_length=16, blank=True)
    email = models.EmailField(blank=True)
    required_service = models.ForeignKey(Service, on_delete=models.SET_NULL, related_name="leads", null=True, blank=True)
    package = models.CharField(max_length=180, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=120, blank=True)
    pincode = models.CharField(max_length=12, blank=True)
    source = models.CharField(max_length=32, choices=LeadSource.choices, default=LeadSource.MANUAL)
    status = models.CharField(max_length=32, choices=LeadStatus.choices, default=LeadStatus.NEW)
    assigned_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="assigned_leads",
        null=True,
        blank=True,
    )
    preferred_callback_at = models.DateTimeField(null=True, blank=True)
    follow_up_at = models.DateTimeField(null=True, blank=True)
    customer_notes = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)
    converted_booking = models.OneToOneField(
        Booking,
        on_delete=models.SET_NULL,
        related_name="source_lead",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_leads",
        null=True,
        blank=True,
        editable=False,
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["primary_mobile"]),
            models.Index(fields=["source", "status"]),
            models.Index(fields=["status", "follow_up_at"]),
            models.Index(fields=["pincode"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.customer_name} ({self.primary_mobile})"

    def clean(self):
        errors = {}
        if self.status == LeadStatus.CONVERTED and self.converted_booking_id is None:
            errors["converted_booking"] = "Converted leads must be linked to a booking."
        if self.converted_booking_id and self.status != LeadStatus.CONVERTED:
            errors["status"] = "A lead with a converted booking must have converted status."
        if self.status in ACTIVE_LEAD_STATUSES:
            duplicate = Lead.objects.filter(primary_mobile=self.primary_mobile, status__in=ACTIVE_LEAD_STATUSES)
            if self.pk:
                duplicate = duplicate.exclude(pk=self.pk)
            if duplicate.exists():
                errors["primary_mobile"] = "An active lead already exists for this mobile number."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def is_follow_up_due(self):
        return bool(self.follow_up_at and self.follow_up_at <= timezone.now() and self.status in ACTIVE_LEAD_STATUSES)


class LeadStatusHistory(BaseModel):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="status_history")
    from_status = models.CharField(max_length=32, blank=True)
    to_status = models.CharField(max_length=32, choices=LeadStatus.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="lead_status_changes",
        null=True,
        blank=True,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("created_at",)
        verbose_name_plural = "lead status histories"
        indexes = [
            models.Index(fields=["lead", "created_at"]),
            models.Index(fields=["to_status"]),
        ]

    def __str__(self):
        return f"{self.lead_id}: {self.from_status} -> {self.to_status}"


class HomepageBannerPlacement(models.TextChoices):
    MAIN = "MAIN", "Main banner"
    PROMOTIONAL_CAROUSEL = "PROMOTIONAL_CAROUSEL", "Promotional carousel"
    CATEGORY = "CATEGORY", "Category banner"
    SERVICE_PAGE = "SERVICE_PAGE", "Service-page banner"


class HomepageBanner(BaseModel):
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    desktop_image = models.ImageField(
        upload_to="banners/desktop/",
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
    )
    mobile_image = models.ImageField(
        upload_to="banners/mobile/",
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
        blank=True,
    )
    image_alt_text = models.CharField(max_length=255)
    button_text = models.CharField(max_length=80, blank=True)
    button_link = models.CharField(max_length=255, blank=True)
    placement = models.CharField(max_length=32, choices=HomepageBannerPlacement.choices, default=HomepageBannerPlacement.MAIN)
    display_order = models.PositiveIntegerField(default=0)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("placement", "display_order", "-created_at")
        indexes = [
            models.Index(fields=["placement", "is_active", "display_order"]),
            models.Index(fields=["starts_at", "ends_at"]),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "End date must be after start date."})
        if self.button_link and not (
            self.button_link.startswith("/")
            or self.button_link.startswith("https://")
            or self.button_link.startswith("http://")
        ):
            raise ValidationError({"button_link": "Use an internal path or full URL."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def is_live(self):
        now = timezone.now()
        return self.is_active and (self.starts_at is None or self.starts_at <= now) and (self.ends_at is None or self.ends_at >= now)


class FAQ(BaseModel):
    question = models.CharField(max_length=255)
    answer = models.TextField()
    category = models.ForeignKey(ServiceCategory, on_delete=models.SET_NULL, related_name="faqs", null=True, blank=True)
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, related_name="faqs", null=True, blank=True)
    package = models.CharField(max_length=180, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("display_order", "question")
        constraints = [
            models.UniqueConstraint(
                fields=["question", "category", "service"],
                condition=Q(is_active=True),
                name="unique_active_faq_context",
            )
        ]
        indexes = [
            models.Index(fields=["is_active", "display_order"]),
            models.Index(fields=["category", "service"]),
        ]

    def __str__(self):
        return self.question
