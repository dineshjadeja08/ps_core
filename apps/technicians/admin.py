from django.contrib import admin

from apps.technicians.models import TechnicianAssignment, TechnicianProfile, TechnicianSkill


@admin.register(TechnicianSkill)
class TechnicianSkillAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at")


@admin.register(TechnicianProfile)
class TechnicianProfileAdmin(admin.ModelAdmin):
    list_display = ("employee_code", "display_name", "phone", "is_available", "is_active", "joined_at")
    list_filter = ("is_available", "is_active", "skills", "service_areas")
    search_fields = ("employee_code", "display_name", "phone", "user__phone_number")
    filter_horizontal = ("skills", "service_areas")
    readonly_fields = ("created_at", "updated_at")


@admin.register(TechnicianAssignment)
class TechnicianAssignmentAdmin(admin.ModelAdmin):
    list_display = ("booking", "technician", "assigned_by", "assigned_at", "unassigned_at")
    list_filter = ("assigned_at", "unassigned_at", "technician")
    search_fields = ("booking__booking_number", "technician__display_name", "technician__employee_code")
    readonly_fields = ("assigned_at", "created_at", "updated_at")
