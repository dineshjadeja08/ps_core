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
    SERVICE_VIEW = "SERVICE_VIEW", "Service view"
    CART = "CART", "Cart"
    CHECKOUT = "CHECKOUT", "Checkout"
    ADMIN = "ADMIN", "Admin"
    PHONE_CALL = "PHONE_CALL", "Phone call"
    CAMPAIGN = "CAMPAIGN", "Campaign"
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


class LeadFunnelStatus(models.TextChoices):
    VISITED = "VISITED", "Visited"
    CART_ADDED = "CART_ADDED", "Cart added"
    UNPAID = "UNPAID", "Unpaid"
    PAID = "PAID", "Paid"
    BOOKED = "BOOKED", "Booked"
    CANCELLED = "CANCELLED", "Cancelled"
    LOST = "LOST", "Lost"


class LeadPaymentStatus(models.TextChoices):
    NOT_REQUIRED = "NOT_REQUIRED", "Not required"
    PENDING = "PENDING", "Pending"
    LINK_SENT = "LINK_SENT", "Link sent"
    PAID = "PAID", "Paid"
    FAILED = "FAILED", "Failed"
    REFUNDED = "REFUNDED", "Refunded"


class LeadTemperature(models.TextChoices):
    HOT = "HOT", "Hot"
    WARM = "WARM", "Warm"
    COLD = "COLD", "Cold"


class LeadActivityAction(models.TextChoices):
    SERVICE_VIEWED = "SERVICE_VIEWED", "Service viewed"
    ADDED_TO_CART = "ADDED_TO_CART", "Added to cart"
    CHECKOUT_STARTED = "CHECKOUT_STARTED", "Checkout started"
    BOOKING_CREATED = "BOOKING_CREATED", "Booking created"
    PAYMENT_LINK_CREATED = "PAYMENT_LINK_CREATED", "Payment link created"
    PAYMENT_LINK_SENT = "PAYMENT_LINK_SENT", "Payment link sent"
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED", "Payment confirmed"
    STATUS_CHANGED = "STATUS_CHANGED", "Status changed"
    CALL_COMPLETED = "CALL_COMPLETED", "Call completed"
    NOTE_ADDED = "NOTE_ADDED", "Note added"
    LEAD_ASSIGNED = "LEAD_ASSIGNED", "Lead assigned"
    LEAD_MERGED = "LEAD_MERGED", "Lead merged"
    MANUAL_PAYMENT_RECORDED = "MANUAL_PAYMENT_RECORDED", "Manual payment recorded"


class ManualPaymentMethod(models.TextChoices):
    MANUAL_CASH = "MANUAL_CASH", "Manual cash"
    MANUAL_UPI = "MANUAL_UPI", "Manual UPI"
    MANUAL_CARD = "MANUAL_CARD", "Manual card"
    MANUAL_BANK_TRANSFER = "MANUAL_BANK_TRANSFER", "Manual bank transfer"


ACTIVE_LEAD_STATUSES = {
    LeadStatus.NEW,
    LeadStatus.CONTACTED,
    LeadStatus.INTERESTED,
    LeadStatus.FOLLOW_UP,
}


class Lead(BaseModel):
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="leads",
        null=True,
        blank=True,
    )
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
    funnel_status = models.CharField(max_length=32, choices=LeadFunnelStatus.choices, default=LeadFunnelStatus.VISITED)
    payment_status = models.CharField(max_length=32, choices=LeadPaymentStatus.choices, default=LeadPaymentStatus.NOT_REQUIRED)
    lead_temperature = models.CharField(max_length=8, choices=LeadTemperature.choices, default=LeadTemperature.WARM)
    assigned_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="assigned_leads",
        null=True,
        blank=True,
    )
    preferred_callback_at = models.DateTimeField(null=True, blank=True)
    preferred_date = models.DateField(null=True, blank=True)
    preferred_slot = models.CharField(max_length=120, blank=True)
    quoted_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    advance_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    balance_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    payment_link_url = models.URLField(blank=True)
    payment_link_provider_id = models.CharField(max_length=128, blank=True)
    payment_link_expires_at = models.DateTimeField(null=True, blank=True)
    last_contacted_at = models.DateTimeField(null=True, blank=True)
    follow_up_at = models.DateTimeField(null=True, blank=True)
    customer_notes = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)
    admin_notes = models.TextField(blank=True)
    lost_reason = models.CharField(max_length=255, blank=True)
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_activity_at = models.DateTimeField(default=timezone.now)
    converted_booking = models.OneToOneField(
        Booking,
        on_delete=models.SET_NULL,
        related_name="source_lead",
        null=True,
        blank=True,
    )
    pending_booking = models.OneToOneField(
        Booking,
        on_delete=models.SET_NULL,
        related_name="pending_source_lead",
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
            models.Index(fields=["customer", "required_service", "funnel_status"]),
            models.Index(fields=["primary_mobile"]),
            models.Index(fields=["funnel_status"]),
            models.Index(fields=["payment_status"]),
            models.Index(fields=["source"]),
            models.Index(fields=["assigned_staff"]),
            models.Index(fields=["source", "status"]),
            models.Index(fields=["status", "follow_up_at"]),
            models.Index(fields=["follow_up_at"]),
            models.Index(fields=["pincode"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["last_activity_at"]),
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
            if self.required_service_id:
                duplicate = duplicate.filter(required_service_id=self.required_service_id)
            if self.pk:
                duplicate = duplicate.exclude(pk=self.pk)
            if duplicate.exists():
                errors["primary_mobile"] = "An active lead already exists for this mobile number and service."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def is_follow_up_due(self):
        return bool(self.follow_up_at and self.follow_up_at <= timezone.now() and self.status in ACTIVE_LEAD_STATUSES)


class LeadActivity(BaseModel):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="activities")
    action = models.CharField(max_length=48, choices=LeadActivityAction.choices)
    previous_value = models.JSONField(default=dict, blank=True)
    new_value = models.JSONField(default=dict, blank=True)
    note = models.TextField(blank=True)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="lead_activities",
        null=True,
        blank=True,
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ("created_at",)
        verbose_name_plural = "lead activities"
        indexes = [
            models.Index(fields=["lead", "created_at"]),
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["performed_by", "created_at"]),
        ]

    def __str__(self):
        return f"{self.lead_id}: {self.action}"


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
