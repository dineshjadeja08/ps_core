from django.contrib import admin

from apps.payments.models import Invoice, InvoiceSequence, Payment


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


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "booking", "customer_name", "total_amount", "issued_at")
    search_fields = ("invoice_number", "booking__booking_number", "customer_name", "customer_phone")
    readonly_fields = ("created_at", "updated_at", "issued_at")


@admin.register(InvoiceSequence)
class InvoiceSequenceAdmin(admin.ModelAdmin):
    list_display = ("financial_year", "current_number")
