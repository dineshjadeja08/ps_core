from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.locations.models import Address, normalize_postal_code
from apps.locations.serializers import (
    AddressSerializer,
    ServiceAreaCheckResponseSerializer,
)
from apps.locations.services import enforce_single_default, get_active_service_area


@extend_schema(
    summary="Check service area support",
    description="Checks whether Purple Squad currently supports a postal code.",
    parameters=[OpenApiParameter("postal_code", str, required=True, description="Postal code to check.")],
    responses={status.HTTP_200_OK: ServiceAreaCheckResponseSerializer},
    examples=[
        OpenApiExample(
            "Supported postal code",
            value={
                "postal_code": "635601",
                "is_supported": True,
                "service_area": {
                    "id": "67d9bd9d-31af-4c75-b443-04377885242e",
                    "name": "Tirupattur Central",
                    "city": "Tirupattur",
                    "state": "Tamil Nadu",
                    "country": "India",
                    "postal_code": "635601",
                },
            },
            response_only=True,
        )
    ],
)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def check_service_area(request):
    postal_code = normalize_postal_code(request.query_params.get("postal_code"))
    if not postal_code:
        return Response(
            {"error": {"code": "VALIDATION_ERROR", "message": "postal_code is required.", "details": {}}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    service_area = get_active_service_area(postal_code)
    return Response(
        {
            "postal_code": postal_code,
            "is_supported": service_area is not None,
            "service_area": _serialize_service_area(service_area) if service_area else None,
        }
    )


class AddressViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    lookup_field = "id"
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        return Address.objects.filter(customer=self.request.user, is_active=True).order_by("-is_default", "-created_at")

    def perform_create(self, serializer):
        address = serializer.save()
        enforce_single_default(address)

    def perform_update(self, serializer):
        address = serializer.save()
        enforce_single_default(address)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.is_default = False
        instance.save(update_fields=["is_active", "is_default", "updated_at"])

    @extend_schema(
        summary="List customer addresses",
        description="Returns active saved addresses belonging to the authenticated customer.",
        responses={status.HTTP_200_OK: AddressSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Create customer address",
        description="Creates a saved address for the authenticated customer. Core persistence does not call Google Maps.",
        request=AddressSerializer,
        responses={status.HTTP_201_CREATED: AddressSerializer},
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @extend_schema(
        summary="Get customer address",
        description="Returns one active address owned by the authenticated customer.",
        parameters=[OpenApiParameter("id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
        responses={status.HTTP_200_OK: AddressSerializer},
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        summary="Update customer address",
        description="Partially updates one active address owned by the authenticated customer.",
        parameters=[OpenApiParameter("id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
        request=AddressSerializer,
        responses={status.HTTP_200_OK: AddressSerializer},
    )
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @extend_schema(
        summary="Deactivate customer address",
        description="Soft-deletes an address by marking it inactive.",
        parameters=[OpenApiParameter("id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
        responses={status.HTTP_204_NO_CONTENT: None},
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


def _serialize_service_area(service_area):
    return {
        "id": str(service_area.id),
        "name": service_area.name,
        "city": service_area.city,
        "state": service_area.state,
        "country": service_area.country,
        "postal_code": service_area.postal_code,
    }
