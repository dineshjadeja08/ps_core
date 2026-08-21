from django.contrib import admin

from apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("event", "channel", "recipient", "booking", "status", "provider", "sent_at", "created_at")
    list_filter = ("event", "channel", "status", "provider", "created_at")
    search_fields = ("recipient__phone_number", "booking__booking_number", "title", "message", "provider_message_id")
    readonly_fields = ("created_at", "updated_at", "payload", "error_message", "sent_at")
