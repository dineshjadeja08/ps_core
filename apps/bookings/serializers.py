from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.bookings.models import Booking, BookingStatusHistory
from apps.bookings.services import create_booking, record_balance_collection, reschedule_booking


class BalanceCollectionMethod:
    CASH = "CASH"
    UPI = "UPI"
    CARD_OFFLINE = "CARD_OFFLINE"
    OTHER = "OTHER"

    choices = (
        (CASH, "Cash"),
        (UPI, "UPI"),
        (CARD_OFFLINE, "Card offline"),
        (OTHER, "Other"),
    )


class BookingCreateSerializer(serializers.Serializer):
    service_id = serializers.UUIDField()
    address_id = serializers.UUIDField()
    slot_id = serializers.UUIDField()
    problem_description = serializers.CharField(required=False, allow_blank=True, default="")
    customer_notes = serializers.CharField(required=False, allow_blank=True)
    contact_phone = serializers.CharField(required=False, allow_blank=True, max_length=20)
    quantity = serializers.IntegerField(required=False, default=1, min_value=1, max_value=20)

    def create(self, validated_data):
        return create_booking(
            customer=self.context["request"].user,
            service_id=validated_data["service_id"],
            address_id=validated_data["address_id"],
            slot_id=validated_data["slot_id"],
            problem_description=validated_data.get("problem_description", ""),
            customer_notes=validated_data.get("customer_notes", ""),
            contact_phone=validated_data.get("contact_phone", ""),
            quantity=validated_data.get("quantity", 1),
        )


class BookingOperationSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True)


class BookingRescheduleSerializer(serializers.Serializer):
    slot_id = serializers.UUIDField()
    notes = serializers.CharField(required=False, allow_blank=True)

    def save(self, **kwargs):
        return reschedule_booking(
            booking_id=self.context["booking_id"],
            slot_id=self.validated_data["slot_id"],
            changed_by=self.context["request"].user,
            notes=self.validated_data.get("notes", ""),
        )


class BalanceCollectionSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    method = serializers.ChoiceField(choices=BalanceCollectionMethod.choices)
    notes = serializers.CharField(required=False, allow_blank=True)

    def save(self, **kwargs):
        booking, payment = record_balance_collection(
            booking_id=self.context["booking_id"],
            amount=self.validated_data["amount"],
            method=self.validated_data["method"],
            changed_by=self.context["request"].user,
            notes=self.validated_data.get("notes", ""),
        )
        self.payment = payment
        return booking


class BookingStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingStatusHistory
        fields = ("id", "from_status", "to_status", "notes", "created_at")


class BookingSerializer(serializers.ModelSerializer):
    service = serializers.SerializerMethodField()
    time_slot = serializers.SerializerMethodField()
    status_history = BookingStatusHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Booking
        fields = (
            "id",
            "booking_number",
            "service",
            "address_snapshot",
            "service_date",
            "time_slot",
            "problem_description",
            "contact_phone",
            "quantity",
            "subtotal",
            "discount_amount",
            "training_fee",
            "tax_amount",
            "total_amount",
            "advance_required",
            "advance_paid",
            "balance_due",
            "balance_collected",
            "payment_status",
            "booking_status",
            "customer_notes",
            "admin_notes",
            "confirmed_at",
            "completed_at",
            "cancelled_at",
            "created_at",
            "updated_at",
            "status_history",
        )

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_service(self, obj):
        return {
            "id": str(obj.service_id),
            "name": obj.service.name,
            "slug": obj.service.slug,
        }

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_time_slot(self, obj):
        return {
            "id": str(obj.time_slot_id),
            "start_time": obj.time_slot.start_time.isoformat(),
            "end_time": obj.time_slot.end_time.isoformat(),
        }


class AdminBookingSerializer(BookingSerializer):
    customer_name = serializers.SerializerMethodField()
    customer_phone = serializers.SerializerMethodField()
    service_category = serializers.CharField(source="service.category.name", read_only=True)
    assigned_technician = serializers.SerializerMethodField()
    paid_at = serializers.SerializerMethodField()

    class Meta(BookingSerializer.Meta):
        fields = BookingSerializer.Meta.fields + (
            "customer_name",
            "customer_phone",
            "service_category",
            "assigned_technician",
            "paid_at",
        )

    @extend_schema_field(OpenApiTypes.STR)
    def get_customer_name(self, obj):
        profile = getattr(obj.customer, "customer_profile", None)
        display_name = (getattr(profile, "display_name", "") or "").strip()
        account_name = " ".join(part for part in (obj.customer.first_name, obj.customer.last_name) if part).strip()
        return display_name or account_name or obj.customer.phone_number

    @extend_schema_field(OpenApiTypes.STR)
    def get_customer_phone(self, obj):
        return obj.contact_phone or obj.customer.phone_number

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_assigned_technician(self, obj):
        user = obj.assigned_technician
        if not user:
            return None
        profile = getattr(user, "technician_profile", None)
        return {
            "id": str(profile.id) if profile else None,
            "user_id": str(user.id),
            "name": profile.display_name if profile else user.phone_number,
            "phone": profile.phone if profile else user.phone_number,
        }

    @extend_schema_field(OpenApiTypes.DATETIME)
    def get_paid_at(self, obj):
        payments = getattr(obj, "successful_payments", None)
        if payments is None:
            payment = obj.payments.filter(status="SUCCESS").order_by("paid_at", "created_at").first()
        else:
            payment = payments[0] if payments else None
        return payment.paid_at if payment else None
