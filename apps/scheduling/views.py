from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.catalogue.models import Service
from apps.locations.models import normalize_postal_code
from apps.locations.services import get_active_service_area
from apps.scheduling.models import TimeSlot
from apps.scheduling.serializers import TimeSlotSerializer
from apps.scheduling.services import get_available_capacity, is_slot_expired


class SlotListView(ListAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = TimeSlotSerializer
    pagination_class = None

    def list(self, request, *args, **kwargs):
        error_response = self._validate_query_params()
        if error_response is not None:
            return error_response
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        service_area = get_active_service_area(self.request.query_params.get("postal_code"))
        if service_area is None:
            return TimeSlot.objects.none()

        queryset = TimeSlot.objects.select_related("service_area").filter(
            service_area=service_area,
            date=self.request.query_params.get("date"),
            is_active=True,
            service_area__is_active=True,
            capacity__gt=0,
        )
        return [slot for slot in queryset.order_by("start_time") if not is_slot_expired(slot) and get_available_capacity(slot) > 0]

    def _validate_query_params(self):
        service_id = self.request.query_params.get("service_id")
        date = self.request.query_params.get("date")
        postal_code = normalize_postal_code(self.request.query_params.get("postal_code"))

        missing = [name for name, value in (("service_id", service_id), ("date", date), ("postal_code", postal_code)) if not value]
        if missing:
            return _validation_error(f"Missing required query parameter(s): {', '.join(missing)}.")

        if not Service.objects.filter(id=service_id, is_active=True, category__is_active=True).exists():
            return _validation_error("Service is not available.", code="SERVICE_NOT_AVAILABLE")

        service_area = get_active_service_area(postal_code)
        if service_area is None:
            return _validation_error(
                "The requested postal code is outside the active service area.",
                code="ADDRESS_OUTSIDE_SERVICE_AREA",
            )

        return None

    @extend_schema(
        summary="List available slots",
        description=(
            "Returns active, future, capacity-available slots for a service, date, and supported postal code. "
            "The frontend availability check is advisory; final booking reservation must still lock the slot."
        ),
        parameters=[
            OpenApiParameter("service_id", str, required=True, description="Service UUID."),
            OpenApiParameter("date", str, required=True, description="Service date in YYYY-MM-DD format."),
            OpenApiParameter("postal_code", str, required=True, description="Customer postal code."),
        ],
        responses={status.HTTP_200_OK: TimeSlotSerializer(many=True)},
        examples=[
            OpenApiExample(
                "Available slot",
                value={
                    "id": "67d9bd9d-31af-4c75-b443-04377885242e",
                    "service_area": "406f0389-df33-4a09-aed7-1fcb66f85321",
                    "date": "2026-08-21",
                    "start_time": "10:00:00",
                    "end_time": "12:00:00",
                    "capacity": 2,
                    "available_capacity": 2,
                },
                response_only=True,
            )
        ],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


def _validation_error(message, code="VALIDATION_ERROR"):
    return Response(
        {"error": {"code": code, "message": message, "details": {}}},
        status=status.HTTP_400_BAD_REQUEST,
    )
