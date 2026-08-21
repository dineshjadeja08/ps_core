from django.contrib import admin

from apps.payments.models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "booking",
        "provider",
        "payment_type",
        "status",
        "amount",
        "currency",
        "provider_order_id",
        "provider_payment_id",
        "signature_verified",
        "paid_at",
    )
    list_filter = ("provider", "payment_type", "status", "signature_verified", "currency")
    search_fields = ("booking__booking_number", "provider_order_id", "provider_payment_id", "idempotency_key")
    readonly_fields = ("created_at", "updated_at", "provider_payload")
