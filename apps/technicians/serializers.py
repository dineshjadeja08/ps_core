from rest_framework import serializers
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field

from apps.technicians.models import TechnicianAssignment, TechnicianProfile, TechnicianSkill


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
