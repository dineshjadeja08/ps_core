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
    problem_description = serializers.CharField()
    customer_notes = serializers.CharField(required=False, allow_blank=True)

    def create(self, validated_data):
        return create_booking(
            customer=self.context["request"].user,
            service_id=validated_data["service_id"],
            address_id=validated_data["address_id"],
            slot_id=validated_data["slot_id"],
            problem_description=validated_data["problem_description"],
            customer_notes=validated_data.get("customer_notes", ""),
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
            "subtotal",
            "discount_amount",
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
