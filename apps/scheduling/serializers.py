from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.scheduling.models import TimeSlot
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
