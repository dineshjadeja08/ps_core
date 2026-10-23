from rest_framework import serializers
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field

from apps.bookings.models import Booking
from apps.bookings.serializers import BookingSerializer
from apps.catalogue.models import Service
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
    preferred_time_slot = serializers.UUIDField(read_only=True)
    service_items = serializers.JSONField(write_only=True, required=False)

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
            "preferred_time_slot",
            "service_items",
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
        items = obj.service_items or ([{"service_id": str(obj.required_service_id), "quantity": 1}] if obj.required_service_id else [])
        services = {str(key): service for key, service in Service.objects.filter(id__in=[item.get("service_id") for item in items]).in_bulk().items()}
        return [
            {
                "service_id": str(service.id),
                "package_name": service.name,
                "quantity": int(item.get("quantity", 1)),
                "unit_cost": str(service.effective_price),
                "line_total": str(service.effective_price * int(item.get("quantity", 1))),
            }
            for item in items
            if (service := services.get(str(item.get("service_id")))) is not None
        ]

    def validate_service_items(self, value):
        if not isinstance(value, list) or not value:
            raise serializers.ValidationError("Select at least one service.")
        normalized = []
        for item in value:
            if not isinstance(item, dict) or set(item) - {"service_id", "quantity"}:
                raise serializers.ValidationError("Each service item needs a service_id and quantity.")
            try:
                service_id = str(serializers.UUIDField().run_validation(item.get("service_id")))
                quantity = int(item.get("quantity", 1))
            except (KeyError, TypeError, ValueError):
                raise serializers.ValidationError("Each service item needs a valid service_id and quantity.")
            if quantity < 1 or quantity > 20:
                raise serializers.ValidationError("Service quantity must be between 1 and 20.")
            if not Service.objects.filter(id=service_id, is_active=True, category__is_active=True).exists():
                raise serializers.ValidationError(f"Service {service_id} is not active.")
            normalized.append({"service_id": service_id, "quantity": quantity})
        if len({item["service_id"] for item in normalized}) != len(normalized):
            raise serializers.ValidationError("Each service may appear only once; use quantity for multiples.")
        return normalized

    def validate(self, attrs):
        attrs = super().validate(attrs)
        service_items = attrs.get("service_items")
        primary = attrs.get("required_service", getattr(self.instance, "required_service", None))
        if service_items and not primary:
            raise serializers.ValidationError({"required_service": "Choose a primary service for the selected service items."})
        if service_items and primary:
            if self.instance and self.instance.pending_booking_id and service_items != self.instance.service_items:
                raise serializers.ValidationError({"service_items": "Service items cannot be changed after a payment booking has been created. Update the schedule or cancel that booking first."})
            item_services = Service.objects.filter(id__in=[item["service_id"] for item in service_items]).select_related("category")
            if any(service.category_id != primary.category_id for service in item_services):
                raise serializers.ValidationError({"service_items": "All selected services must belong to the primary service category."})
            if str(primary.id) not in {item["service_id"] for item in service_items}:
                raise serializers.ValidationError({"service_items": "The primary service must be included in the selected items."})
        return attrs

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_subtotal(self, obj):
        if obj.service_items:
            return sum((service.effective_price * int(item.get("quantity", 1)) for item, service in self._service_item_pairs(obj)), start=0)
        if obj.quoted_amount is not None:
            return obj.quoted_amount
        return obj.required_service.effective_price if obj.required_service else 0

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_tax_amount(self, obj):
        return 0

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_training_fee(self, obj):
        if obj.service_items:
            return sum((service.training_fee * int(item.get("quantity", 1) if service.training_fee_per_unit else 1) for item, service in self._service_item_pairs(obj)), start=0)
        return obj.required_service.training_fee if obj.required_service else 0

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_total_amount(self, obj):
        return self.get_subtotal(obj) + self.get_training_fee(obj)

    def _service_item_pairs(self, obj):
        items = obj.service_items or []
        services = {str(key): service for key, service in Service.objects.filter(id__in=[item.get("service_id") for item in items]).in_bulk().items()}
        return [(item, services[str(item["service_id"])]) for item in items if str(item.get("service_id")) in services]


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
    slot_id = serializers.UUIDField(required=False)


class LeadReminderSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=("SMS",), default="SMS")


class LeadContactSerializer(serializers.Serializer):
    note = serializers.CharField()
    next_follow_up_at = serializers.DateTimeField(required=False)


class LeadPaymentLinkSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=("SMS", "WHATSAPP"), default="SMS")
    payment_scope = serializers.ChoiceField(choices=("FULL", "ADVANCE"), default="ADVANCE")
    whatsapp_consent_confirmed = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if attrs["channel"] == "WHATSAPP" and not attrs.get("whatsapp_consent_confirmed"):
            raise serializers.ValidationError({"whatsapp_consent_confirmed": "Confirm that the customer agreed to receive this WhatsApp message."})
        return attrs


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
    recent_bookings = BookingSerializer(many=True)
    pending_payments = BookingSerializer(many=True)
    unassigned_items = BookingSerializer(many=True)


class AdminGlobalSearchSerializer(serializers.Serializer):
    query = serializers.CharField()
    results = serializers.ListField(child=serializers.DictField())


class AdminSettingsSerializer(serializers.Serializer):
    debug = serializers.BooleanField()
    allowed_hosts = serializers.ListField(child=serializers.CharField())
    cors_allowed_origins = serializers.ListField(child=serializers.CharField())
    csrf_trusted_origins = serializers.ListField(child=serializers.CharField())
    notification_provider = serializers.CharField()
    razorpay_configured = serializers.BooleanField()
    firebase_configured = serializers.BooleanField()
    msg91_configured = serializers.BooleanField()
    google_maps_configured = serializers.BooleanField()
    cloudinary_media_enabled = serializers.BooleanField()
    cloudinary_media_configured = serializers.BooleanField()
    booking_require_balance_before_completion = serializers.BooleanField()
