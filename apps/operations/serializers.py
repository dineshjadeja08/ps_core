from rest_framework import serializers
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field

from apps.bookings.models import Booking
from apps.bookings.serializers import BookingSerializer
from apps.operations.models import FAQ, HomepageBanner, Lead, LeadStatusHistory


class LeadStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = LeadStatusHistory
        fields = ("id", "from_status", "to_status", "changed_by", "notes", "created_at")
        read_only_fields = fields


class LeadSerializer(serializers.ModelSerializer):
    status_history = LeadStatusHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Lead
        fields = (
            "id",
            "customer_name",
            "primary_mobile",
            "alternate_mobile",
            "email",
            "required_service",
            "package",
            "address",
            "city",
            "pincode",
            "source",
            "status",
            "assigned_staff",
            "preferred_callback_at",
            "follow_up_at",
            "customer_notes",
            "internal_notes",
            "converted_booking",
            "created_by",
            "created_at",
            "updated_at",
            "status_history",
        )
        read_only_fields = ("id", "created_by", "created_at", "updated_at", "status_history")


class LeadConvertSerializer(serializers.Serializer):
    booking_id = serializers.UUIDField()
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_booking_id(self, value):
        try:
            return Booking.objects.get(id=value)
        except Booking.DoesNotExist as exc:
            raise serializers.ValidationError("Booking was not found.") from exc


class FAQSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = (
            "id",
            "question",
            "answer",
            "category",
            "service",
            "package",
            "display_order",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class HomepageBannerSerializer(serializers.ModelSerializer):
    desktop_image_url = serializers.SerializerMethodField()
    mobile_image_url = serializers.SerializerMethodField()

    class Meta:
        model = HomepageBanner
        fields = (
            "id",
            "title",
            "description",
            "desktop_image",
            "desktop_image_url",
            "mobile_image",
            "mobile_image_url",
            "image_alt_text",
            "button_text",
            "button_link",
            "placement",
            "display_order",
            "starts_at",
            "ends_at",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "desktop_image_url", "mobile_image_url", "created_at", "updated_at")

    @extend_schema_field(OpenApiTypes.URI)
    def get_desktop_image_url(self, obj):
        request = self.context.get("request")
        if not obj.desktop_image:
            return ""
        url = obj.desktop_image.url
        return request.build_absolute_uri(url) if request else url

    @extend_schema_field(OpenApiTypes.URI)
    def get_mobile_image_url(self, obj):
        request = self.context.get("request")
        if not obj.mobile_image:
            return ""
        url = obj.mobile_image.url
        return request.build_absolute_uri(url) if request else url


class AdminReportSummarySerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    daily_bookings = serializers.IntegerField()
    completed_services = serializers.IntegerField()
    cancelled_bookings = serializers.IntegerField()
    payment_pending_bookings = serializers.IntegerField()
    revenue_collected = serializers.DecimalField(max_digits=12, decimal_places=2)
    advance_payments = serializers.DecimalField(max_digits=12, decimal_places=2)
    balance_payments = serializers.DecimalField(max_digits=12, decimal_places=2)
    refunds = serializers.DecimalField(max_digits=12, decimal_places=2)
    unassigned_bookings = serializers.IntegerField()
    average_rating = serializers.FloatField()


class AdminSettingsSerializer(serializers.Serializer):
    debug = serializers.BooleanField()
    allowed_hosts = serializers.ListField(child=serializers.CharField())
    cors_allowed_origins = serializers.ListField(child=serializers.CharField())
    csrf_trusted_origins = serializers.ListField(child=serializers.CharField())
    otp_provider = serializers.CharField()
    notification_provider = serializers.CharField()
    razorpay_configured = serializers.BooleanField()
    msg91_configured = serializers.BooleanField()
    firebase_configured = serializers.BooleanField()
    cloudinary_media_enabled = serializers.BooleanField()
    cloudinary_media_configured = serializers.BooleanField()
    booking_require_balance_before_completion = serializers.BooleanField()
