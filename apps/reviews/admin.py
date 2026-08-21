from django.contrib import admin

from apps.reviews.models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("booking", "customer", "technician", "rating", "is_visible", "created_at")
    list_filter = ("rating", "is_visible", "created_at")
    search_fields = ("booking__booking_number", "customer__phone_number", "technician__phone_number", "comment")
    readonly_fields = ("created_at", "updated_at")
