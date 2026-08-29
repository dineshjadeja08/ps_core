from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from apps.bookings.models import Booking, BookingStatusHistory
from apps.notifications.models import Notification
from apps.payments.models import Payment


class BookingStatusHistoryInline(admin.TabularInline):
    model = BookingStatusHistory
    extra = 0
    readonly_fields = ("from_status", "to_status", "changed_by", "notes", "created_at", "updated_at")
    can_delete = False


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    can_delete = False
    readonly_fields = (
        "provider",
        "payment_type",
        "status",
        "amount",
        "currency",
        "provider_order_id",
        "provider_payment_id",
        "signature_verified",
        "paid_at",
        "created_at",
    )
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


class NotificationInline(admin.TabularInline):
    model = Notification
    extra = 0
    can_delete = False
    readonly_fields = ("event", "channel", "status", "send_attempts", "provider", "provider_message_id", "error_message", "sent_at", "created_at")
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "booking_number",
        "customer_link",
        "customer_mobile",
        "service",
        "package_name",
        "service_date",
        "slot_window",
        "booking_status",
        "payment_status",
        "assigned_technician",
        "source",
        "total_amount",
        "advance_required",
        "balance_due",
        "created_at",
    )
    list_filter = (
        "booking_status",
        "payment_status",
        "service__category",
        "service",
        "assigned_technician",
        "service_date",
        "created_at",
    )
    search_fields = (
        "booking_number",
        "customer__phone_number",
        "customer__first_name",
        "customer__last_name",
        "service__name",
        "problem_description",
        "payments__provider_order_id",
        "payments__provider_payment_id",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "address_snapshot",
        "customer_link",
        "customer_mobile",
        "slot_window",
        "source",
    )
    autocomplete_fields = ("customer", "service", "address", "time_slot", "assigned_technician")
    date_hierarchy = "created_at"
    inlines = (PaymentInline, NotificationInline, BookingStatusHistoryInline)
    list_select_related = ("customer", "service", "service__category", "time_slot", "assigned_technician")
    fieldsets = (
        ("Customer information", {"fields": ("customer", "customer_link", "customer_mobile", "address", "address_snapshot")}),
        ("Service and schedule", {"fields": ("service", "service_date", "time_slot", "slot_window", "assigned_technician")}),
        ("Pricing", {"fields": ("subtotal", "discount_amount", "tax_amount", "total_amount", "advance_required", "advance_paid", "balance_due", "balance_collected")}),
        ("Status", {"fields": ("booking_status", "payment_status", "confirmed_at", "completed_at", "cancelled_at")}),
        ("Notes", {"fields": ("problem_description", "customer_notes", "admin_notes")}),
        ("System", {"fields": ("source", "created_at", "updated_at")}),
    )

    @admin.display(description="Customer")
    def customer_link(self, obj):
        url = reverse("admin:accounts_user_change", args=[obj.customer_id])
        return format_html('<a href="{}">{}</a>', url, obj.customer)

    @admin.display(description="Mobile")
    def customer_mobile(self, obj):
        return obj.customer.phone_number

    @admin.display(description="Package")
    def package_name(self, obj):
        return obj.service.name

    @admin.display(description="Date and slot")
    def slot_window(self, obj):
        return f"{obj.service_date} {obj.time_slot.start_time:%H:%M}-{obj.time_slot.end_time:%H:%M}"

    @admin.display(description="Source")
    def source(self, obj):
        return "Lead" if hasattr(obj, "source_lead") else "Customer"


@admin.register(BookingStatusHistory)
class BookingStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("booking", "from_status", "to_status", "changed_by", "created_at")
    list_filter = ("to_status", "created_at")
    search_fields = ("booking__booking_number", "notes")
    readonly_fields = ("created_at", "updated_at")
