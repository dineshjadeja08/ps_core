from django.contrib import admin

from apps.locations.models import Address, ServiceArea


@admin.register(ServiceArea)
class ServiceAreaAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "state", "postal_code", "country", "is_active")
    list_filter = ("is_active", "city", "state", "country")
    search_fields = ("name", "city", "state", "postal_code")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("label", "customer", "recipient_name", "city", "postal_code", "is_default", "is_active")
    list_filter = ("is_active", "is_default", "city", "state", "country")
    search_fields = ("customer__phone_number", "recipient_name", "phone", "postal_code", "address_line_1")
    readonly_fields = ("created_at", "updated_at")
