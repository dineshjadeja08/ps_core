from django.contrib import admin
from django.utils.html import format_html

from apps.catalogue.models import AdvancePaymentType, Service, ServiceCategory, ServiceImage


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
    readonly_fields = ("created_at", "updated_at", "advance_amount", "cover_preview")
    fieldsets = (
        ("Service", {"fields": ("category", "name", "slug", "short_description", "description")}),
        ("Content sections", {"fields": ("whats_included", "whats_excluded", "important_notes")}),
        ("Pricing", {"fields": ("base_price", "selling_price", "advance_payment_type", "advance_payment_value", "advance_amount")}),
        ("Media", {"fields": ("cover_image", "cover_preview")}),
        ("Display", {"fields": ("estimated_duration_minutes", "display_order", "is_featured", "is_popular", "is_active")}),
        ("System", {"fields": ("created_at", "updated_at")}),
    )
    autocomplete_fields = ("category",)

    @admin.display(description="Cover preview")
    def cover_preview(self, obj):
        if not obj.cover_image:
            return "-"
        return format_html('<img src="{}" style="max-width:220px;max-height:140px;border-radius:8px;" />', obj.cover_image.url)

    def save_model(self, request, obj, form, change):
        effective_price = obj.selling_price if obj.selling_price is not None else obj.base_price
        advance_value = obj.advance_payment_value or 0
        if obj.advance_payment_type == AdvancePaymentType.PERCENTAGE:
            obj.advance_amount = effective_price * advance_value / 100
        else:
            obj.advance_amount = advance_value
        super().save_model(request, obj, form, change)


class ServiceImageInline(admin.TabularInline):
    model = ServiceImage
    extra = 0
    fields = ("image", "preview", "alt_text", "display_order", "is_active")
    readonly_fields = ("preview",)

    @admin.display(description="Preview")
    def preview(self, obj):
        if not obj.image:
            return "-"
        return format_html('<img src="{}" style="max-width:120px;max-height:80px;border-radius:8px;" />', obj.image.url)


ServiceAdmin.inlines = (ServiceImageInline,)


@admin.register(ServiceImage)
class ServiceImageAdmin(admin.ModelAdmin):
    list_display = ("service", "alt_text", "display_order", "is_active", "updated_at")
    list_filter = ("is_active", "service__category")
    search_fields = ("service__name", "alt_text")
    ordering = ("service", "display_order")
    readonly_fields = ("created_at", "updated_at")
