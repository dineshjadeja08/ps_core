from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.scheduling.models import ScheduleClosure, TimeSlot
from apps.scheduling.services import get_available_capacity


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
