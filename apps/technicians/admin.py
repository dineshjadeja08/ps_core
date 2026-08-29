from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from apps.audit.models import AuditAction
from apps.audit.services import audit_event
from apps.technicians.models import (
    TechnicianAssignment,
    TechnicianAvailabilityStatus,
    TechnicianLeave,
    TechnicianProfile,
    TechnicianSkill,
    TechnicianVerificationStatus,
    TechnicianWorkingHours,
)


@admin.register(TechnicianSkill)
class TechnicianSkillAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at")


@admin.register(TechnicianProfile)
class TechnicianProfileAdmin(admin.ModelAdmin):
    list_display = (
        "employee_code",
        "display_name",
        "phone",
        "technician_type",
        "background_verification_status",
        "availability_status",
        "is_available",
        "is_active",
        "completed_job_count",
        "average_rating",
    )
    list_filter = (
        "technician_type",
        "employment_status",
        "background_verification_status",
        "availability_status",
        "is_available",
        "is_active",
        "skills",
        "service_areas",
        "supported_services",
        "city",
        "pincode",
    )
    search_fields = ("employee_code", "display_name", "phone", "alternate_phone", "email", "user__phone_number")
    filter_horizontal = ("skills", "service_areas", "supported_services")
    readonly_fields = ("created_at", "updated_at", "profile_photo_preview", "id_document_available", "address_document_available")
    autocomplete_fields = ("user",)
    actions = ("approve_technicians", "reject_technicians", "suspend_technicians", "reactivate_technicians")
    fieldsets = (
        ("Identity", {"fields": ("user", "employee_code", "display_name", "profile_photo", "profile_photo_preview")}),
        ("Contact", {"fields": ("phone", "alternate_phone", "email", "address", "city", "pincode")}),
        ("Work profile", {"fields": ("technician_type", "employment_status", "joined_at", "experience_years", "languages")}),
        ("Coverage", {"fields": ("supported_services", "service_areas", "skills")}),
        (
            "Verification",
            {
                "fields": (
                    "id_proof_type",
                    "id_proof_number",
                    "id_proof_document",
                    "id_document_available",
                    "address_proof_document",
                    "address_document_available",
                    "background_verification_status",
                )
            },
        ),
        ("Availability", {"fields": ("availability_status", "is_available", "is_active")}),
        ("Performance", {"fields": ("average_rating", "completed_job_count", "cancellation_count")}),
        ("Internal", {"fields": ("internal_notes", "created_at", "updated_at")}),
    )

    @admin.display(description="Photo")
    def profile_photo_preview(self, obj):
        if not obj.profile_photo:
            return "-"
        return format_html('<img src="{}" style="max-width:96px;max-height:96px;border-radius:8px;" />', obj.profile_photo.url)

    @admin.display(description="ID document")
    def id_document_available(self, obj):
        return "Uploaded" if obj.id_proof_document else "-"

    @admin.display(description="Address proof")
    def address_document_available(self, obj):
        return "Uploaded" if obj.address_proof_document else "-"

    def save_model(self, request, obj, form, change):
        previous_verification = None
        previous_availability = None
        if change and obj.pk:
            previous = TechnicianProfile.objects.filter(pk=obj.pk).values(
                "background_verification_status",
                "availability_status",
            ).first()
            if previous:
                previous_verification = previous["background_verification_status"]
                previous_availability = previous["availability_status"]
        obj.full_clean()
        super().save_model(request, obj, form, change)

        action = AuditAction.TECHNICIAN_UPDATED if change else AuditAction.TECHNICIAN_CREATED
        metadata = {
            "employee_code": obj.employee_code,
            "verification_status": obj.background_verification_status,
            "availability_status": obj.availability_status,
        }
        if previous_verification and previous_verification != obj.background_verification_status:
            action = AuditAction.TECHNICIAN_VERIFICATION_CHANGED
            metadata["from_verification_status"] = previous_verification
        elif previous_availability and previous_availability != obj.availability_status:
            action = AuditAction.TECHNICIAN_AVAILABILITY_CHANGED
            metadata["from_availability_status"] = previous_availability
        audit_event(
            action=action,
            actor=request.user,
            request=request,
            resource_type="technician",
            resource_id=obj.id,
            metadata=metadata,
        )

    def _set_status(self, request, queryset, *, verification=None, availability=None, active=None, available=None, label):
        count = queryset.update(
            **{
                key: value
                for key, value in {
                    "background_verification_status": verification,
                    "availability_status": availability,
                    "is_active": active,
                    "is_available": available,
                    "updated_at": timezone.now(),
                }.items()
                if value is not None
            }
        )
        for technician in queryset:
            audit_event(
                action=AuditAction.TECHNICIAN_VERIFICATION_CHANGED if verification else AuditAction.TECHNICIAN_AVAILABILITY_CHANGED,
                actor=request.user,
                request=request,
                resource_type="technician",
                resource_id=technician.id,
                metadata={"bulk_action": label},
            )
        self.message_user(request, f"{count} technicians marked {label}.")

    @admin.action(description="Approve selected technicians")
    def approve_technicians(self, request, queryset):
        self._set_status(
            request,
            queryset,
            verification=TechnicianVerificationStatus.VERIFIED,
            availability=TechnicianAvailabilityStatus.AVAILABLE,
            active=True,
            available=True,
            label="approved",
        )

    @admin.action(description="Reject selected technicians")
    def reject_technicians(self, request, queryset):
        self._set_status(request, queryset, verification=TechnicianVerificationStatus.REJECTED, active=False, available=False, label="rejected")

    @admin.action(description="Suspend selected technicians")
    def suspend_technicians(self, request, queryset):
        self._set_status(
            request,
            queryset,
            verification=TechnicianVerificationStatus.SUSPENDED,
            availability=TechnicianAvailabilityStatus.SUSPENDED,
            active=False,
            available=False,
            label="suspended",
        )

    @admin.action(description="Reactivate selected technicians")
    def reactivate_technicians(self, request, queryset):
        self._set_status(
            request,
            queryset,
            verification=TechnicianVerificationStatus.UNDER_REVIEW,
            availability=TechnicianAvailabilityStatus.OFFLINE,
            active=True,
            available=False,
            label="reactivated",
        )


@admin.register(TechnicianWorkingHours)
class TechnicianWorkingHoursAdmin(admin.ModelAdmin):
    list_display = ("technician", "day_of_week", "start_time", "end_time", "is_active")
    list_filter = ("day_of_week", "is_active")
    search_fields = ("technician__display_name", "technician__employee_code")
    autocomplete_fields = ("technician",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(TechnicianLeave)
class TechnicianLeaveAdmin(admin.ModelAdmin):
    list_display = ("technician", "start_at", "end_at", "reason", "approved_by", "is_active")
    list_filter = ("is_active", "start_at", "end_at")
    search_fields = ("technician__display_name", "technician__employee_code", "reason")
    autocomplete_fields = ("technician", "approved_by")
    readonly_fields = ("created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        if obj.approved_by_id is None:
            obj.approved_by = request.user
        obj.full_clean()
        super().save_model(request, obj, form, change)
        audit_event(
            action=AuditAction.TECHNICIAN_LEAVE_CREATED,
            actor=request.user,
            request=request,
            resource_type="technician_leave",
            resource_id=obj.id,
            metadata={"technician_id": str(obj.technician_id), "is_active": obj.is_active},
        )


@admin.register(TechnicianAssignment)
class TechnicianAssignmentAdmin(admin.ModelAdmin):
    list_display = ("booking", "technician", "previous_technician", "assigned_by", "assigned_at", "unassigned_at", "reason")
    list_filter = ("assigned_at", "unassigned_at", "technician", "previous_technician")
    search_fields = ("booking__booking_number", "technician__display_name", "technician__employee_code")
    autocomplete_fields = ("booking", "technician", "previous_technician", "assigned_by")
    readonly_fields = ("assigned_at", "created_at", "updated_at")
