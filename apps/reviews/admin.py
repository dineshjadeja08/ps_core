from django.contrib import admin

from apps.reviews.models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("booking", "service", "reviewer_name", "customer", "rating", "is_visible", "created_at")
    list_filter = ("service", "rating", "is_visible", "created_at")
    search_fields = ("booking__booking_number", "service__name", "reviewer_name", "customer__phone_number", "comment")
    readonly_fields = ("created_at", "updated_at")
