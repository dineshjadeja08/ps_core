from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models

from common.models import BaseModel


class AdvancePaymentType(models.TextChoices):
    FIXED = "FIXED", "Fixed amount"
    PERCENTAGE = "PERCENTAGE", "Percentage"


class ServiceCategory(BaseModel):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=180, unique=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="categories/", blank=True)
    image_url = models.URLField(blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("display_order", "name")
        verbose_name_plural = "service categories"
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active", "display_order"]),
        ]

    def __str__(self):
        return self.name


class Service(BaseModel):
    category = models.ForeignKey(ServiceCategory, on_delete=models.PROTECT, related_name="services")
    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=220, unique=True)
    short_description = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    whats_included = models.TextField(blank=True)
    whats_excluded = models.TextField(blank=True)
    important_notes = models.TextField(blank=True)
    landing_group = models.CharField(max_length=120, blank=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    advance_payment_type = models.CharField(
        max_length=16,
        choices=AdvancePaymentType.choices,
        default=AdvancePaymentType.FIXED,
    )
    advance_payment_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    advance_amount = models.DecimalField(max_digits=10, decimal_places=2)
    training_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    training_fee_per_unit = models.BooleanField(default=False)
    estimated_duration_minutes = models.PositiveIntegerField()
    cover_image = models.ImageField(upload_to="services/covers/", blank=True)
    landing_thumbnail = models.ImageField(upload_to="services/landing-thumbnails/", blank=True)
    popup_cover_image = models.ImageField(upload_to="services/popup-covers/", blank=True)
    popup_content_image = models.ImageField(upload_to="services/popup-content/", blank=True)
    list_image = models.ImageField(upload_to="services/list-images/", blank=True)
    is_featured = models.BooleanField(default=False)
    is_popular = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("category__display_order", "display_order", "name")
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active", "is_featured", "display_order"]),
            models.Index(fields=["is_active", "is_popular"]),
            models.Index(fields=["category", "is_active"]),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}
        if self.base_price is not None and self.base_price < Decimal("0.00"):
            errors["base_price"] = "Base price cannot be negative."
        if self.selling_price is not None and self.selling_price < Decimal("0.00"):
            errors["selling_price"] = "Selling price cannot be negative."
        if self.advance_amount is not None and self.advance_amount < Decimal("0.00"):
            errors["advance_amount"] = "Advance amount cannot be negative."
        if self.advance_payment_value is not None and self.advance_payment_value < Decimal("0.00"):
            errors["advance_payment_value"] = "Advance payment value cannot be negative."
        if self.training_fee is not None and self.training_fee < Decimal("0.00"):
            errors["training_fee"] = "Training fee cannot be negative."
        if (
            self.advance_payment_type == AdvancePaymentType.PERCENTAGE
            and self.advance_payment_value is not None
            and self.advance_payment_value > Decimal("100.00")
        ):
            errors["advance_payment_value"] = "Advance percentage cannot exceed 100."
        if (
            self.effective_price is not None
            and self.advance_amount is not None
            and self.advance_amount > self.effective_price
        ):
            errors["advance_amount"] = "Advance amount cannot exceed service price."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def effective_price(self):
        return self.selling_price if self.selling_price is not None else self.base_price


class ServiceImage(BaseModel):
    service = models.ForeignKey(Service, related_name="images", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="services/gallery/")
    alt_text = models.CharField(max_length=255, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("display_order", "created_at")
        indexes = [
            models.Index(fields=["service", "is_active", "display_order"]),
        ]

    def __str__(self):
        return f"{self.service.name} image"


class Package(BaseModel):
    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=220, unique=True)
    description = models.TextField(blank=True)
    bundle_price = models.DecimalField(max_digits=10, decimal_places=2)
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    maximum_usage_limit = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    services = models.ManyToManyField(Service, through="PackageItem", related_name="packages")

    class Meta:
        ordering = ("name",)
        indexes = [
            models.Index(fields=["is_active", "valid_from", "valid_until"]),
            models.Index(fields=["slug"]),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}
        if self.bundle_price is not None and self.bundle_price < Decimal("0.00"):
            errors["bundle_price"] = "Bundle price cannot be negative."
        if self.maximum_usage_limit is not None and self.maximum_usage_limit < 1:
            errors["maximum_usage_limit"] = "Maximum usage limit must be at least 1."
        if self.valid_from and self.valid_until and self.valid_from > self.valid_until:
            errors["valid_until"] = "Validity end date must be on or after the start date."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class PackageItem(BaseModel):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name="items")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="package_items")
    quantity = models.PositiveIntegerField(default=1)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("display_order", "created_at")
        constraints = [
            models.UniqueConstraint(fields=["package", "service"], name="unique_package_service"),
        ]
        indexes = [models.Index(fields=["package", "display_order"])]

    def __str__(self):
        return f"{self.package.name}: {self.quantity} × {self.service.name}"

    def clean(self):
        if self.quantity is not None and self.quantity < 1:
            raise ValidationError({"quantity": "Quantity must be at least 1."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
