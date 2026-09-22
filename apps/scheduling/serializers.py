from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.scheduling.models import ScheduleClosure, TimeSlot
from apps.scheduling.services import count_reserved_bookings, get_available_capacity


class TimeSlotSerializer(serializers.ModelSerializer):
    available_capacity = serializers.SerializerMethodField()
    service_area = serializers.UUIDField(source="service_area_id", read_only=True)

    class Meta:
        model = TimeSlot
        fields = (
            "id",
            "service_area",
            "date",
            "start_time",
            "end_time",
            "capacity",
            "available_capacity",
        )

    @extend_schema_field(OpenApiTypes.INT)
    def get_available_capacity(self, obj):
        return get_available_capacity(obj)


class AdminTimeSlotSerializer(TimeSlotSerializer):
    service_area_name = serializers.CharField(source="service_area.name", read_only=True)

    class Meta(TimeSlotSerializer.Meta):
        fields = TimeSlotSerializer.Meta.fields + ("service_area_name", "is_active")

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is None:
            return attrs

        schedule_fields = ("date", "start_time", "end_time")
        schedule_changed = any(
            field in attrs and attrs[field] != getattr(self.instance, field)
            for field in schedule_fields
        )
        if schedule_changed and self.instance.bookings.exists():
            raise serializers.ValidationError(
                {"date": "A slot linked to a booking cannot have its date or time changed."}
            )

        capacity = attrs.get("capacity", self.instance.capacity)
        reserved = count_reserved_bookings(self.instance)
        if capacity < reserved:
            raise serializers.ValidationError(
                {"capacity": f"Capacity cannot be lower than the {reserved} current reservation(s)."}
            )
        return attrs


class ScheduleClosureSerializer(serializers.ModelSerializer):
    service_area_name = serializers.CharField(source="service_area.name", read_only=True)

    class Meta:
        model = ScheduleClosure
        fields = (
            "id",
            "service_area",
            "service_area_name",
            "closure_type",
            "start_date",
            "end_date",
            "reason",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "service_area_name", "created_at", "updated_at")
