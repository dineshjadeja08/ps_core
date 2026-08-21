from django.contrib import admin

from apps.scheduling.models import TimeSlot


@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = ("service_area", "date", "start_time", "end_time", "capacity", "is_active")
    list_filter = ("is_active", "date", "service_area__city", "service_area")
    search_fields = ("service_area__name", "service_area__postal_code", "service_area__city")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("date", "start_time")
