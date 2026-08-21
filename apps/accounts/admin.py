from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.accounts.models import CustomerProfile, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("phone_number",)
    list_display = ("phone_number", "email", "role", "is_verified", "is_active", "is_staff")
    list_filter = ("role", "is_verified", "is_active", "is_staff")
    search_fields = ("phone_number", "email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("phone_number", "password")}),
        ("Personal info", {"fields": ("email", "first_name", "last_name")}),
        ("Purple Squad", {"fields": ("role", "is_verified")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    readonly_fields = ("created_at", "updated_at", "last_login")
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("phone_number", "password1", "password2", "role", "is_verified", "is_staff", "is_superuser"),
            },
        ),
    )


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "display_name", "alternate_phone", "created_at")
    search_fields = ("user__phone_number", "display_name", "alternate_phone")
    readonly_fields = ("created_at", "updated_at")
