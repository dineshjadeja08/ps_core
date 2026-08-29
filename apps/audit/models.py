from django.conf import settings
from django.db import models

from common.models import BaseModel


class AuditAction(models.TextChoices):
    ADMIN_BOOKING_START = "ADMIN_BOOKING_START", "Admin booking start"
    ADMIN_BOOKING_COMPLETE = "ADMIN_BOOKING_COMPLETE", "Admin booking complete"
    ADMIN_BOOKING_CANCEL = "ADMIN_BOOKING_CANCEL", "Admin booking cancel"
    ADMIN_RECORD_BALANCE = "ADMIN_RECORD_BALANCE", "Admin record balance"
    TECHNICIAN_ASSIGN = "TECHNICIAN_ASSIGN", "Technician assign"
    TECHNICIAN_CREATED = "TECHNICIAN_CREATED", "Technician created"
    TECHNICIAN_UPDATED = "TECHNICIAN_UPDATED", "Technician updated"
    TECHNICIAN_VERIFICATION_CHANGED = "TECHNICIAN_VERIFICATION_CHANGED", "Technician verification changed"
    TECHNICIAN_AVAILABILITY_CHANGED = "TECHNICIAN_AVAILABILITY_CHANGED", "Technician availability changed"
    TECHNICIAN_ASSIGNMENT_REMOVED = "TECHNICIAN_ASSIGNMENT_REMOVED", "Technician assignment removed"
    TECHNICIAN_LEAVE_CREATED = "TECHNICIAN_LEAVE_CREATED", "Technician leave created"
    PAYMENT_WEBHOOK_RECEIVED = "PAYMENT_WEBHOOK_RECEIVED", "Payment webhook received"
    PAYMENT_WEBHOOK_REJECTED = "PAYMENT_WEBHOOK_REJECTED", "Payment webhook rejected"
    PERMISSION_DENIED = "PERMISSION_DENIED", "Permission denied"
    SERVICE_CREATED = "SERVICE_CREATED", "Service created"
    SERVICE_UPDATED = "SERVICE_UPDATED", "Service updated"
    SERVICE_DEACTIVATED = "SERVICE_DEACTIVATED", "Service deactivated"
    SERVICE_PRICE_CHANGED = "SERVICE_PRICE_CHANGED", "Service price changed"
    SERVICE_IMAGE_CHANGED = "SERVICE_IMAGE_CHANGED", "Service image changed"
    CATEGORY_CREATED = "CATEGORY_CREATED", "Category created"
    CATEGORY_UPDATED = "CATEGORY_UPDATED", "Category updated"
    CATEGORY_DEACTIVATED = "CATEGORY_DEACTIVATED", "Category deactivated"
    LEAD_CREATED = "LEAD_CREATED", "Lead created"
    LEAD_UPDATED = "LEAD_UPDATED", "Lead updated"
    LEAD_STATUS_CHANGED = "LEAD_STATUS_CHANGED", "Lead status changed"
    LEAD_CONVERTED = "LEAD_CONVERTED", "Lead converted"
    BANNER_CREATED = "BANNER_CREATED", "Banner created"
    BANNER_UPDATED = "BANNER_UPDATED", "Banner updated"
    BANNER_PUBLICATION_CHANGED = "BANNER_PUBLICATION_CHANGED", "Banner publication changed"
    FAQ_CREATED = "FAQ_CREATED", "FAQ created"
    FAQ_UPDATED = "FAQ_UPDATED", "FAQ updated"


class AuditLog(BaseModel):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=64, choices=AuditAction.choices)
    resource_type = models.CharField(max_length=64)
    resource_id = models.CharField(max_length=128, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["actor", "created_at"]),
            models.Index(fields=["resource_type", "resource_id"]),
            models.Index(fields=["request_id"]),
        ]

    def __str__(self):
        return f"{self.action} {self.resource_type}:{self.resource_id}"
