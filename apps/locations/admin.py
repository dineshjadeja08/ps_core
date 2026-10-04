from django.contrib import admin

from apps.locations.models import Address, ServiceArea, ServiceAreaLocality


class ServiceAreaLocalityInline(admin.TabularInline):
    model = ServiceAreaLocality
    extra = 0
    fields = ("name", "slug", "is_active", "display_order")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ServiceArea)
class ServiceAreaAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "state", "postal_code", "country", "is_active")
    list_filter = ("is_active", "city", "state", "country")
    search_fields = ("name", "city", "state", "postal_code")
    readonly_fields = ("created_at", "updated_at")
    filter_horizontal = ("services",)
    inlines = (ServiceAreaLocalityInline,)


@admin.register(ServiceAreaLocality)
class ServiceAreaLocalityAdmin(admin.ModelAdmin):
    list_display = ("name", "service_area", "postal_code", "city", "is_active", "display_order")
    list_filter = ("is_active", "service_area__city", "service_area__state")
    search_fields = ("name", "slug", "service_area__postal_code", "service_area__city")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("service_area",)
    readonly_fields = ("created_at", "updated_at")

    @admin.display(ordering="service_area__postal_code")
    def postal_code(self, obj):
        return obj.service_area.postal_code

    @admin.display(ordering="service_area__city")
    def city(self, obj):
        return obj.service_area.city


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("label", "customer", "recipient_name", "city", "postal_code", "is_default", "is_active")
    list_filter = ("is_active", "is_default", "city", "state", "country")
    search_fields = ("customer__phone_number", "recipient_name", "phone", "postal_code", "address_line_1")
    readonly_fields = ("created_at", "updated_at")
