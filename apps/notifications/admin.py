from django.contrib import admin
from django.utils import timezone

from apps.notifications.models import Notification, NotificationStatus
from apps.notifications.services import send_notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("event", "channel", "recipient", "booking", "status", "send_attempts", "provider", "sent_at", "created_at")
    list_filter = ("event", "channel", "status", "provider", "created_at")
    search_fields = ("recipient__phone_number", "booking__booking_number", "title", "message", "provider_message_id")
    readonly_fields = ("created_at", "updated_at", "payload", "error_message", "sent_at", "send_attempts", "provider_message_id")
    date_hierarchy = "created_at"
    actions = ("retry_failed_notifications", "cancel_queued_notifications")
    list_select_related = ("recipient", "booking")

    @admin.action(description="Retry selected failed notifications")
    def retry_failed_notifications(self, request, queryset):
        count = 0
        for notification in queryset.filter(status=NotificationStatus.FAILED):
            send_notification(notification)
            count += 1
        self.message_user(request, f"Retried {count} failed notifications.")

    @admin.action(description="Cancel selected queued notifications")
    def cancel_queued_notifications(self, request, queryset):
        count = queryset.filter(status=NotificationStatus.QUEUED).update(status=NotificationStatus.CANCELLED, updated_at=timezone.now())
        self.message_user(request, f"Cancelled {count} queued notifications.")
