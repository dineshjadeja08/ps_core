from django.utils import timezone
from rest_framework import serializers
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field

from apps.technicians.models import TechnicianAssignment, TechnicianLeave, TechnicianProfile, TechnicianSkill


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


class TechnicianLeaveRequestSerializer(serializers.Serializer):
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()
    reason = serializers.CharField(max_length=160)

    def validate(self, attrs):
        if attrs["start_at"] >= attrs["end_at"]:
            raise serializers.ValidationError({"end_at": "End time must be after start time."})
        if attrs["end_at"] <= timezone.now():
            raise serializers.ValidationError({"start_at": "Leave must be in the future."})
        return attrs


class TechnicianReviewSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    booking_number = serializers.CharField(source="booking.booking_number", read_only=True)
    customer_name = serializers.SerializerMethodField()
    service_name = serializers.CharField(source="booking.service.name", read_only=True)
    rating = serializers.IntegerField(read_only=True)
    comment = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    @extend_schema_field(OpenApiTypes.STR)
    def get_customer_name(self, obj):
        # First name only: technicians don't need the customer's full identity after the job.
        profile = getattr(obj.customer, "customer_profile", None)
        name = (profile.display_name if profile else "") or obj.customer.first_name
        return name.split(" ")[0] if name else "Customer"


class TechnicianTrendPointSerializer(serializers.Serializer):
    month = serializers.CharField()
    jobs = serializers.IntegerField()
    earnings = serializers.FloatField()
    rating = serializers.FloatField(allow_null=True)


class TechnicianPerformanceSerializer(serializers.Serializer):
    period = serializers.CharField()
    completion_rate = serializers.IntegerField()
    completed = serializers.IntegerField()
    total = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    open = serializers.IntegerField()
    gross_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    average_rating = serializers.FloatField(allow_null=True)
    review_count = serializers.IntegerField()
    penalties = serializers.IntegerField(allow_null=True)
    penalty_amount = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    needs_attention = serializers.BooleanField()
    trend = TechnicianTrendPointSerializer(many=True)
