from django.contrib import admin

from apps.audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "actor", "resource_type", "resource_id", "request_id", "ip_address", "created_at")
    list_filter = ("action", "resource_type", "created_at")
    search_fields = ("actor__phone_number", "resource_id", "request_id", "ip_address")
    readonly_fields = ("created_at", "updated_at", "metadata")
