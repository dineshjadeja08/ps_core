from django.contrib import admin

from apps.catalogue.models import Service, ServiceCategory, ServiceImage


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "display_order", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("display_order", "name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "base_price",
        "selling_price",
        "advance_amount",
        "advance_payment_type",
        "advance_payment_value",
        "estimated_duration_minutes",
        "is_featured",
        "is_popular",
        "is_active",
        "display_order",
        "updated_at",
    )
    list_filter = ("is_active", "is_featured", "is_popular", "category")
    search_fields = ("name", "slug", "short_description", "description")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("category__display_order", "display_order", "name")
    readonly_fields = ("created_at", "updated_at")


class ServiceImageInline(admin.TabularInline):
    model = ServiceImage
    extra = 0
    fields = ("image", "alt_text", "display_order", "is_active")


ServiceAdmin.inlines = (ServiceImageInline,)


@admin.register(ServiceImage)
class ServiceImageAdmin(admin.ModelAdmin):
    list_display = ("service", "alt_text", "display_order", "is_active", "updated_at")
    list_filter = ("is_active", "service__category")
    search_fields = ("service__name", "alt_text")
    ordering = ("service", "display_order")
    readonly_fields = ("created_at", "updated_at")
