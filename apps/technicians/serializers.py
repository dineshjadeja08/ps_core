from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field

from apps.technicians.models import (
    JobPhoto,
    JobPhotoKind,
    PrivateTechnicianDocument,
    PrivateTechnicianDocumentStatus,
    PrivateTechnicianDocumentType,
    TechnicianAssignment,
    TechnicianCompanyUser,
    TechnicianDocument,
    TechnicianDocumentType,
    TechnicianLeave,
    TechnicianProfile,
    TechnicianSkill,
)
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
            "whatsapp_notifications_enabled",
            "is_active",
            "joined_at",
            "id_document_available",
            "address_document_available",
            "kyc_submitted_at",
            "verification_note",
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
    sales_person_assigned_name = serializers.SerializerMethodField()
    active_job_count = serializers.IntegerField(read_only=True, default=0)
    completed_jobs = serializers.IntegerField(read_only=True, default=0)
    monthly_job_count = serializers.IntegerField(read_only=True, default=0)
    yearly_job_count = serializers.IntegerField(read_only=True, default=0)
    cancelled_jobs = serializers.IntegerField(read_only=True, default=0)
    approved_rating = serializers.DecimalField(max_digits=3, decimal_places=2, read_only=True, allow_null=True)
    approved_review_count = serializers.IntegerField(read_only=True, default=0)
    eligibility_errors = serializers.ListField(child=serializers.CharField(), read_only=True, default=list)

    class Meta(TechnicianProfileSerializer.Meta):
        fields = TechnicianProfileSerializer.Meta.fields + (
            "address", "internal_notes", "active_job_count", "completed_jobs", "monthly_job_count", "yearly_job_count", "cancelled_jobs",
            "approved_rating", "approved_review_count", "eligibility_errors", "virtual_mobile_number", "service_group", "profile_type",
            "lead_per_day", "job_per_day", "no_of_teams", "sales_person_assigned", "sales_person_assigned_name", "crm_owner_id",
        )

    @extend_schema_field(OpenApiTypes.STR)
    def get_sales_person_assigned_name(self, obj):
        if not obj.sales_person_assigned_id:
            return ""
        return " ".join(filter(None, [obj.sales_person_assigned.first_name, obj.sales_person_assigned.last_name])).strip() or obj.sales_person_assigned.phone_number


class AdminTechnicianDetailSerializer(AdminTechnicianProfileSerializer):
    class Meta(AdminTechnicianProfileSerializer.Meta):
        fields = AdminTechnicianProfileSerializer.Meta.fields + ("id_proof_type", "id_proof_number")


class AdminTechnicianWriteSerializer(serializers.ModelSerializer):
    employee_code = serializers.CharField(max_length=40, required=False, allow_blank=True)
    id_proof_number = serializers.CharField(max_length=120, required=False, allow_blank=True, trim_whitespace=True)
    skill_names = serializers.ListField(child=serializers.CharField(max_length=120), required=False, write_only=True)
    service_area_ids = serializers.PrimaryKeyRelatedField(
        source="service_areas", queryset=ServiceArea.objects.all(), many=True, required=False, write_only=True,
    )
    supported_service_ids = serializers.PrimaryKeyRelatedField(
        source="supported_services", queryset=Service.objects.all(), many=True, required=False, write_only=True,
    )
    experience_years = serializers.DecimalField(max_digits=4, decimal_places=1, min_value=0, required=False)
    sales_person_assigned = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_staff=True, is_active=True, role__in=[UserRole.ADMIN, UserRole.SUPER_ADMIN]),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = TechnicianProfile
        fields = (
            "employee_code", "display_name", "profile_photo", "phone", "alternate_phone", "email", "address", "city", "pincode", "id_proof_number",
            "virtual_mobile_number", "service_group", "profile_type", "lead_per_day", "job_per_day", "no_of_teams", "sales_person_assigned", "crm_owner_id",
            "technician_type", "employment_status", "experience_years", "languages", "joined_at",
            "background_verification_status", "availability_status", "is_active", "internal_notes", "whatsapp_notifications_enabled",
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

    def validate_id_proof_number(self, value):
        if value and (not value.isdigit() or len(value) != 12):
            raise serializers.ValidationError("Enter a valid 12-digit Aadhaar number.")
        return value

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
        if "id_proof_number" in attrs:
            attrs["id_proof_type"] = "AADHAAR" if attrs["id_proof_number"] else ""
        return attrs

    def _save(self, data, instance=None):
        skills = data.pop("skill_names", None)
        try:
            with transaction.atomic():
                if instance is None:
                    if not data.get("employee_code"):
                        import uuid

                        code = ""
                        while not code or TechnicianProfile.objects.filter(employee_code=code).exists():
                            code = f"PS-T-{uuid.uuid4().hex[:8].upper()}"
                        data["employee_code"] = code
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


class PrivateTechnicianDocumentSerializer(serializers.ModelSerializer):
    content_url = serializers.SerializerMethodField()
    uploaded_by_name = serializers.SerializerMethodField()
    verified_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PrivateTechnicianDocument
        fields = (
            "id", "document_type", "original_name", "content_type", "file_size", "verification_status",
            "verification_note", "uploaded_by_name", "verified_by_name", "verified_at", "created_at", "content_url",
        )
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.URI)
    def get_content_url(self, obj):
        request = self.context.get("request")
        path = f"/api/v1/admin/technicians/{obj.technician_id}/documents/{obj.id}/content/"
        return request.build_absolute_uri(path) if request else path

    def get_uploaded_by_name(self, obj):
        return _user_label(obj.uploaded_by)

    def get_verified_by_name(self, obj):
        return _user_label(obj.verified_by)


class PrivateTechnicianDocumentUploadSerializer(serializers.Serializer):
    document_type = serializers.ChoiceField(choices=PrivateTechnicianDocumentType.choices)
    file = serializers.FileField(allow_empty_file=False)

    def validate_file(self, uploaded):
        allowed = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
        if uploaded.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("File must be 10 MB or smaller.")
        content_type = getattr(uploaded, "content_type", "")
        if content_type not in allowed:
            raise serializers.ValidationError("Upload a PDF, JPG, PNG or WebP document.")
        header = uploaded.read(16)
        uploaded.seek(0)
        signatures = {
            "application/pdf": lambda value: value.startswith(b"%PDF-"),
            "image/jpeg": lambda value: value.startswith(b"\xff\xd8\xff"),
            "image/png": lambda value: value.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/webp": lambda value: len(value) >= 12 and value[:4] == b"RIFF" and value[8:12] == b"WEBP",
        }
        if not signatures[content_type](header):
            raise serializers.ValidationError("The file contents do not match the selected document type.")
        return uploaded


class PrivateTechnicianDocumentVerificationSerializer(serializers.Serializer):
    verification_status = serializers.ChoiceField(choices=("VERIFIED", "REJECTED"))
    verification_note = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    def validate(self, attrs):
        if attrs["verification_status"] == "REJECTED" and not attrs.get("verification_note", "").strip():
            raise serializers.ValidationError({"verification_note": "A note is required when rejecting a document."})
        return attrs


class TechnicianCompanyUserSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    phone_number = serializers.CharField(source="user.phone_number", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = TechnicianCompanyUser
        fields = ("id", "name", "phone_number", "email", "role", "is_active", "created_at")
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.STR)
    def get_name(self, obj):
        return _user_label(obj.user)


class TechnicianCompanyUserCreateSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=16)
    role = serializers.ChoiceField(choices=("OWNER", "MANAGER", "STAFF"))

    def validate_phone_number(self, value):
        value = normalize_phone_number(value)
        try:
            self._user = User.objects.get(phone_number=value)
        except User.DoesNotExist as exc:
            raise serializers.ValidationError("No account exists for this phone number. Create the account first.") from exc
        if self._user.role == UserRole.SUPER_ADMIN:
            raise serializers.ValidationError("Super-admin accounts cannot be assigned as company users.")
        return value

    def create(self, validated_data):
        technician = self.context["technician"]
        membership, created = TechnicianCompanyUser.objects.get_or_create(
            technician=technician,
            user=self._user,
            defaults={"role": validated_data["role"]},
        )
        if not created:
            raise serializers.ValidationError({"phone_number": "This account is already added to this company."})
        return membership


def _user_label(user):
    if not user:
        return ""
    return " ".join(filter(None, [user.first_name, user.last_name])).strip() or user.phone_number
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


class StartJobSerializer(serializers.Serializer):
    otp = serializers.RegexField(r"^\d{4}$", error_messages={"invalid": "Enter the 4-digit OTP from the customer."})
    notes = serializers.CharField(required=False, allow_blank=True)


class JobPhotoSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = JobPhoto
        fields = ("id", "kind", "url", "created_at")
        read_only_fields = ("id", "url", "created_at")

    @extend_schema_field(OpenApiTypes.URI)
    def get_url(self, obj):
        request = self.context.get("request")
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url


class JobPhotoUploadSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=JobPhotoKind.choices)
    file = serializers.FileField()


class TechnicianEarningJobSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    booking_number = serializers.CharField()
    service_name = serializers.CharField()
    service_date = serializers.DateField()
    completed_at = serializers.DateTimeField(allow_null=True)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    paid_online = serializers.DecimalField(max_digits=10, decimal_places=2)
    collected_by_you = serializers.DecimalField(max_digits=10, decimal_places=2)
    collection_method = serializers.CharField(allow_blank=True)


class TechnicianEarningsSerializer(serializers.Serializer):
    period = serializers.CharField()
    job_count = serializers.IntegerField()
    job_value_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    collected_by_you_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    paid_online_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    jobs = TechnicianEarningJobSerializer(many=True)


class TechnicianProfileUpdateSerializer(serializers.Serializer):
    display_name = serializers.CharField(max_length=150, required=False)
    email = serializers.EmailField(required=False, allow_blank=True)
    alternate_phone = serializers.CharField(max_length=16, required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False)
    pincode = serializers.RegexField(r"^\d{6}$", required=False, error_messages={"invalid": "Enter a 6-digit pincode."})
    experience_years = serializers.DecimalField(max_digits=4, decimal_places=1, min_value=0, max_value=60, required=False)
    languages = serializers.ListField(child=serializers.CharField(max_length=40), required=False, max_length=10)
    skill_ids = serializers.ListField(child=serializers.UUIDField(), required=False, max_length=30)

    def validate_skill_ids(self, value):
        skills = list(TechnicianSkill.objects.filter(id__in=value, is_active=True))
        if len(skills) != len(set(value)):
            raise serializers.ValidationError("One or more services were not found.")
        return skills

    def update(self, profile, validated_data):
        skills = validated_data.pop("skill_ids", None)
        for field, value in validated_data.items():
            setattr(profile, field, value)
        profile.save()
        if skills is not None:
            profile.skills.set(skills)
        return profile


class TechnicianDocumentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = TechnicianDocument
        fields = ("id", "doc_type", "url", "created_at")

    @extend_schema_field(OpenApiTypes.URI)
    def get_url(self, obj):
        request = self.context.get("request")
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url


class TechnicianDocumentUploadSerializer(serializers.Serializer):
    doc_type = serializers.ChoiceField(choices=TechnicianDocumentType.choices)
    file = serializers.FileField()


class KycDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=(("APPROVE", "Approve"), ("REJECT", "Reject")))
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)
