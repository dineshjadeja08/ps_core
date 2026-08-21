from django.contrib import admin

from apps.bookings.models import Booking, BookingStatusHistory


class BookingStatusHistoryInline(admin.TabularInline):
    model = BookingStatusHistory
    extra = 0
    readonly_fields = ("from_status", "to_status", "changed_by", "notes", "created_at", "updated_at")
    can_delete = False


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "booking_number",
        "customer",
        "service",
        "service_date",
        "booking_status",
        "payment_status",
        "total_amount",
        "advance_required",
        "balance_due",
    )
    list_filter = ("booking_status", "payment_status", "service_date", "service")
    search_fields = ("booking_number", "customer__phone_number", "problem_description")
    readonly_fields = ("created_at", "updated_at", "address_snapshot")
    inlines = (BookingStatusHistoryInline,)


@admin.register(BookingStatusHistory)
class BookingStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("booking", "from_status", "to_status", "changed_by", "created_at")
    list_filter = ("to_status", "created_at")
    search_fields = ("booking__booking_number", "notes")
    readonly_fields = ("created_at", "updated_at")
