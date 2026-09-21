from rest_framework import serializers
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field

from apps.bookings.models import Booking
from apps.bookings.serializers import BookingSerializer
from apps.operations.models import FAQ, HomepageBanner, Lead, LeadActivity, LeadStatusHistory, ManualPaymentMethod


class LeadStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = LeadStatusHistory
        fields = ("id", "from_status", "to_status", "changed_by", "notes", "created_at")
        read_only_fields = fields


class LeadActivitySerializer(serializers.ModelSerializer):
    performed_by_phone = serializers.CharField(source="performed_by.phone_number", read_only=True)

    class Meta:
        model = LeadActivity
        fields = (
            "id",
            "action",
            "previous_value",
            "new_value",
            "note",
            "performed_by",
            "performed_by_phone",
            "ip_address",
            "created_at",
        )
        read_only_fields = fields


class LeadSerializer(serializers.ModelSerializer):
    status_history = LeadStatusHistorySerializer(many=True, read_only=True)
    activities = LeadActivitySerializer(many=True, read_only=True)
    service_name = serializers.CharField(source="required_service.name", read_only=True)
    assigned_staff_phone = serializers.CharField(source="assigned_staff.phone_number", read_only=True)
    booking_number = serializers.SerializerMethodField()
    lead_number = serializers.SerializerMethodField()
    line_items = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()
    tax_amount = serializers.SerializerMethodField()
    training_fee = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()

    class Meta:
        model = Lead
        fields = (
            "id",
            "lead_number",
            "customer",
            "customer_name",
            "primary_mobile",
            "alternate_mobile",
            "email",
            "required_service",
            "service_name",
            "package",
            "address",
            "city",
            "pincode",
            "source",
            "status",
            "funnel_status",
            "payment_status",
            "lead_temperature",
            "assigned_staff",
            "assigned_staff_phone",
            "preferred_callback_at",
            "preferred_date",
            "preferred_slot",
            "quoted_amount",
            "advance_amount",
            "balance_amount",
            "payment_link_url",
            "payment_link_provider_id",
            "payment_link_expires_at",
            "last_contacted_at",
            "follow_up_at",
            "customer_notes",
            "internal_notes",
            "admin_notes",
            "lost_reason",
            "first_seen_at",
            "last_activity_at",
            "converted_booking",
            "pending_booking",
            "booking_number",
            "line_items",
            "subtotal",
            "tax_amount",
            "training_fee",
            "total_amount",
            "created_by",
            "created_at",
            "updated_at",
            "status_history",
            "activities",
        )
        read_only_fields = (
            "id",
            "created_by",
            "payment_link_provider_id",
            "created_at",
            "updated_at",
            "status_history",
            "activities",
        )

    @extend_schema_field(OpenApiTypes.STR)
    def get_booking_number(self, obj):
        booking = obj.converted_booking or obj.pending_booking
        return booking.booking_number if booking else ""

    @extend_schema_field(OpenApiTypes.STR)
    def get_lead_number(self, obj):
        return f"LD-{str(obj.id).split('-')[0].upper()}"

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_line_items(self, obj):
        service = obj.required_service
        if service is None:
            return []
        return [{
            "service_id": str(service.id),
            "package_name": obj.package or service.name,
            "quantity": 1,
            "unit_cost": str(obj.quoted_amount if obj.quoted_amount is not None else service.effective_price),
        }]

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_subtotal(self, obj):
        if obj.quoted_amount is not None:
            return obj.quoted_amount
        return obj.required_service.effective_price if obj.required_service else 0

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_tax_amount(self, obj):
        return 0

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_training_fee(self, obj):
        return obj.required_service.training_fee if obj.required_service else 0

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_total_amount(self, obj):
        return self.get_subtotal(obj) + self.get_training_fee(obj)


class LeadConvertSerializer(serializers.Serializer):
    booking_id = serializers.UUIDField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_booking_id(self, value):
        try:
            return Booking.objects.get(id=value)
        except Booking.DoesNotExist as exc:
            raise serializers.ValidationError("Booking was not found.") from exc


class LeadScheduleSerializer(serializers.Serializer):
    preferred_date = serializers.DateField()
    preferred_slot = serializers.RegexField(r"^([01]\d|2[0-3]):[0-5]\d$", max_length=5)


class LeadReminderSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=("SMS", "WHATSAPP"), default="SMS")


class LeadContactSerializer(serializers.Serializer):
    note = serializers.CharField()
    next_follow_up_at = serializers.DateTimeField(required=False)


class LeadPaymentLinkSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=("SMS", "WHATSAPP"), default="WHATSAPP")
    payment_scope = serializers.ChoiceField(choices=("FULL", "ADVANCE"), default="ADVANCE")


class LeadManualPaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    method = serializers.ChoiceField(choices=ManualPaymentMethod.choices)
    reference = serializers.CharField(required=False, allow_blank=True)
    payment_date = serializers.DateField()
    note = serializers.CharField(required=False, allow_blank=True)
    confirm = serializers.BooleanField()

    def validate_confirm(self, value):
        if not value:
            raise serializers.ValidationError("Manual payment confirmation is required.")
        return value


class LeadSummarySerializer(serializers.Serializer):
    all_leads = serializers.IntegerField()
    visited = serializers.IntegerField()
    cart_added = serializers.IntegerField()
    unpaid = serializers.IntegerField()
    paid = serializers.IntegerField()
    booked = serializers.IntegerField()
    follow_ups_due_today = serializers.IntegerField()


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


class AdminDashboardSummarySerializer(serializers.Serializer):
    daily_gmv = serializers.DecimalField(max_digits=12, decimal_places=2)
    active_bookings_count = serializers.IntegerField()
    available_technicians_count = serializers.IntegerField()
    open_unassigned_leads_count = serializers.IntegerField()
    leads_today = serializers.IntegerField()
    follow_ups_due = serializers.IntegerField()
    bookings_today = serializers.IntegerField()
    confirmed_bookings = serializers.IntegerField()
    payment_pending_bookings = serializers.IntegerField()
    revenue_today = serializers.DecimalField(max_digits=12, decimal_places=2)
    unassigned_bookings = serializers.IntegerField()
    upcoming_services = serializers.IntegerField()
    failed_notifications = serializers.IntegerField()


class AdminGlobalSearchSerializer(serializers.Serializer):
    query = serializers.CharField()
    results = serializers.ListField(child=serializers.DictField())


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
