from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field

from apps.technicians.models import TechnicianAssignment, TechnicianLeave, TechnicianProfile, TechnicianSkill
from apps.accounts.models import User, UserRole
from apps.accounts.validators import normalize_phone_number
from apps.catalogue.models import Service
from apps.locations.models import ServiceArea


class TechnicianSkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = TechnicianSkill
        fields = ("id", "name", "description")


class TechnicianProfileSerializer(serializers.ModelSerializer):
    skills = TechnicianSkillSerializer(many=True, read_only=True)
    service_areas = serializers.SerializerMethodField()
    supported_services = serializers.SerializerMethodField()
    profile_photo_url = serializers.SerializerMethodField()
    id_document_available = serializers.SerializerMethodField()
    address_document_available = serializers.SerializerMethodField()

    class Meta:
        model = TechnicianProfile
        fields = (
            "id",
            "employee_code",
            "display_name",
            "profile_photo_url",
            "phone",
            "alternate_phone",
            "email",
            "technician_type",
            "employment_status",
            "city",
            "pincode",
            "skills",
            "service_areas",
            "supported_services",
            "experience_years",
            "languages",
            "background_verification_status",
            "availability_status",
            "average_rating",
            "completed_job_count",
            "cancellation_count",
            "is_available",
            "is_active",
            "joined_at",
            "id_document_available",
            "address_document_available",
        )

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_service_areas(self, obj):
        return [
            {
                "id": str(area.id),
                "name": area.name,
                "postal_code": area.postal_code,
                "city": area.city,
            }
            for area in obj.service_areas.all()
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_supported_services(self, obj):
        return [
            {
                "id": str(service.id),
                "name": service.name,
                "slug": service.slug,
                "category": service.category.name,
            }
            for service in obj.supported_services.all()
        ]

    @extend_schema_field(OpenApiTypes.URI)
    def get_profile_photo_url(self, obj):
        request = self.context.get("request")
        if not obj.profile_photo:
            return ""
        url = obj.profile_photo.url
        return request.build_absolute_uri(url) if request else url

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_id_document_available(self, obj):
        return bool(obj.id_proof_document)

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_address_document_available(self, obj):
        return bool(obj.address_proof_document)


class AdminTechnicianProfileSerializer(TechnicianProfileSerializer):
    active_job_count = serializers.IntegerField(read_only=True, default=0)
    completed_jobs = serializers.IntegerField(read_only=True, default=0)
    cancelled_jobs = serializers.IntegerField(read_only=True, default=0)
    approved_rating = serializers.DecimalField(max_digits=3, decimal_places=2, read_only=True, allow_null=True)
    approved_review_count = serializers.IntegerField(read_only=True, default=0)
    eligibility_errors = serializers.ListField(child=serializers.CharField(), read_only=True, default=list)

    class Meta(TechnicianProfileSerializer.Meta):
        fields = TechnicianProfileSerializer.Meta.fields + (
            "address", "internal_notes", "active_job_count", "completed_jobs", "cancelled_jobs",
            "approved_rating", "approved_review_count", "eligibility_errors",
        )


class AdminTechnicianWriteSerializer(serializers.ModelSerializer):
    skill_names = serializers.ListField(child=serializers.CharField(max_length=120), required=False, write_only=True)
    service_area_ids = serializers.PrimaryKeyRelatedField(
        source="service_areas", queryset=ServiceArea.objects.all(), many=True, required=False, write_only=True,
    )
    supported_service_ids = serializers.PrimaryKeyRelatedField(
        source="supported_services", queryset=Service.objects.all(), many=True, required=False, write_only=True,
    )
    experience_years = serializers.DecimalField(max_digits=4, decimal_places=1, min_value=0, required=False)

    class Meta:
        model = TechnicianProfile
        fields = (
            "employee_code", "display_name", "phone", "alternate_phone", "email", "address", "city", "pincode",
            "technician_type", "employment_status", "experience_years", "languages", "joined_at",
            "background_verification_status", "availability_status", "is_active", "internal_notes",
            "skill_names", "service_area_ids", "supported_service_ids",
        )

    def validate_phone(self, value):
        value = normalize_phone_number(value)
        users = User.objects.filter(phone_number=value)
        if self.instance:
            users = users.exclude(pk=self.instance.user_id)
        elif users.filter(role=UserRole.TECHNICIAN, technician_profile__isnull=True).exists():
            return value
        if users.exists():
            raise serializers.ValidationError("This phone number already belongs to another account.")
        return value

    def validate_alternate_phone(self, value):
        return normalize_phone_number(value) if value else ""

    def validate(self, attrs):
        def current(field, default):
            return attrs.get(field, getattr(self.instance, field, default))

        active = current("is_active", True)
        employment = current("employment_status", "ACTIVE")
        if employment != "ACTIVE":
            attrs["is_active"] = active = False
        if active and (
            current("background_verification_status", "PENDING") == "SUSPENDED"
            or current("availability_status", "AVAILABLE") == "SUSPENDED"
        ):
            raise serializers.ValidationError({"is_active": "Deactivate a suspended technician before saving."})
        attrs["is_available"] = active and current("availability_status", "AVAILABLE") == "AVAILABLE"
        return attrs

    def _save(self, data, instance=None):
        skills = data.pop("skill_names", None)
        try:
            with transaction.atomic():
                if instance is None:
                    user, _ = User.objects.select_for_update().get_or_create(
                        phone_number=data["phone"], defaults={"role": UserRole.TECHNICIAN, "password": "!"},
                    )
                    if user.role != UserRole.TECHNICIAN or hasattr(user, "technician_profile"):
                        raise serializers.ValidationError({"phone": "This account cannot be used for a new technician."})
                    instance = super().create({**data, "user": user})
                else:
                    instance = TechnicianProfile.objects.select_for_update().get(pk=instance.pk)
                    # Recompute availability against the locked profile, not a stale GET response.
                    active = data.get("is_active", instance.is_active)
                    employment = data.get("employment_status", instance.employment_status)
                    if employment != "ACTIVE":
                        data["is_active"] = active = False
                    data["is_available"] = active and data.get("availability_status", instance.availability_status) == "AVAILABLE"
                    instance = super().update(instance, data)
                    if instance.user.phone_number != instance.phone:
                        instance.user.phone_number = instance.phone
                        instance.user.firebase_uid = None
                        instance.user.is_verified = False
                        instance.user.save(update_fields=["phone_number", "firebase_uid", "is_verified", "updated_at"])
                if skills is not None:
                    instance.skills.set([TechnicianSkill.objects.get_or_create(name=name)[0] for name in dict.fromkeys(skills)])
                return instance
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages) from exc
        except IntegrityError as exc:
            raise serializers.ValidationError("Employee code or phone is already in use. Reload and try again.") from exc

    def create(self, validated_data):
        return self._save(validated_data)

    def update(self, instance, validated_data):
        return self._save(validated_data, instance)

    def to_representation(self, instance):
        return AdminTechnicianProfileSerializer(instance, context=self.context).data


class AssignTechnicianRequestSerializer(serializers.Serializer):
    technician_id = serializers.UUIDField()
    notes = serializers.CharField(required=False, allow_blank=True)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=160)


class RemoveTechnicianAssignmentRequestSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True)


class TechnicianAssignmentSerializer(serializers.ModelSerializer):
    technician = TechnicianProfileSerializer(read_only=True)

    class Meta:
        model = TechnicianAssignment
        fields = (
            "id",
            "booking",
            "technician",
            "previous_technician",
            "assigned_by",
            "assigned_at",
            "unassigned_at",
            "reason",
            "notification_status",
            "notes",
        )
        read_only_fields = fields


class TechnicianLeaveReviewSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True)


class TechnicianLeaveSerializer(serializers.ModelSerializer):
    technician_name = serializers.CharField(source="technician.display_name", read_only=True)
    technician_employee_code = serializers.CharField(source="technician.employee_code", read_only=True)
    approved_by_phone = serializers.CharField(source="approved_by.phone_number", read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = TechnicianLeave
        fields = (
            "id",
            "technician",
            "technician_name",
            "technician_employee_code",
            "start_at",
            "end_at",
            "reason",
            "status",
            "approved_by",
            "approved_by_phone",
            "review_note",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.STR)
    def get_status(self, obj):
        if not obj.is_active:
            return "REJECTED"
        return "APPROVED" if obj.approved_by_id else "PENDING"
