from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from django.db import transaction
from rest_framework import generics, status, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsAdminRole
from apps.audit.models import AuditAction
from apps.audit.services import audit_event
from apps.bookings.models import Booking
from apps.catalogue.models import Service, ServiceCategory, ServiceImage
from apps.catalogue.serializers import (
    AdminServiceCategorySerializer,
    AdminServiceSerializer,
    ServiceCategorySerializer,
    ServiceDetailSerializer,
    ServiceImageSerializer,
    ServiceListSerializer,
)


class ServiceCategoryListView(generics.ListAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = ServiceCategorySerializer
    pagination_class = None

    def get_queryset(self):
        return ServiceCategory.objects.filter(is_active=True).order_by("display_order", "name")

    @extend_schema(
        summary="List service categories",
        description="Returns active service categories ordered for public display.",
        responses={status.HTTP_200_OK: ServiceCategorySerializer(many=True)},
        examples=[
            OpenApiExample(
                "Categories",
                value={
                    "id": "67d9bd9d-31af-4c75-b443-04377885242e",
                    "name": "AC Service",
                    "slug": "ac-service",
                    "description": "Routine AC inspection and cleaning.",
                    "image_url": "https://example.com/ac-service.jpg",
                    "display_order": 1,
                },
                response_only=True,
            )
        ],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ServiceListView(generics.ListAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = ServiceListSerializer

    def get_queryset(self):
        queryset = (
            Service.objects.select_related("category")
            .filter(is_active=True, category__is_active=True)
            .order_by("category__display_order", "name")
        )

        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category__slug=category)

        featured = self.request.query_params.get("featured")
        if featured is not None:
            queryset = queryset.filter(is_featured=featured.lower() in {"1", "true", "yes"})

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search.strip())

        return queryset

    @extend_schema(
        summary="List services",
        description="Returns active public services with optional category, featured, and name search filters.",
        parameters=[
            OpenApiParameter("category", str, description="Filter by category slug."),
            OpenApiParameter("featured", bool, description="Filter featured services."),
            OpenApiParameter("search", str, description="Search by service name."),
        ],
        responses={status.HTTP_200_OK: ServiceListSerializer(many=True)},
        examples=[
            OpenApiExample(
                "Service list item",
                value={
                    "id": "67d9bd9d-31af-4c75-b443-04377885242e",
                    "category": {
                        "id": "406f0389-df33-4a09-aed7-1fcb66f85321",
                        "name": "AC Service",
                        "slug": "ac-service",
                        "description": "Routine AC services.",
                        "image_url": "",
                        "display_order": 1,
                    },
                    "name": "AC General Service",
                    "slug": "ac-general-service",
                    "short_description": "Cleaning and inspection for split AC units.",
                    "base_price": "1499.00",
                    "advance_amount": "299.00",
                    "estimated_duration_minutes": 90,
                    "is_featured": True,
                },
                response_only=True,
            )
        ],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ServiceDetailView(generics.RetrieveAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = ServiceDetailSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return Service.objects.select_related("category").filter(is_active=True, category__is_active=True)

    @extend_schema(
        summary="Get service detail",
        description="Returns one active public service by slug.",
        responses={status.HTTP_200_OK: ServiceDetailSerializer},
        examples=[
            OpenApiExample(
                "Service detail",
                value={
                    "id": "67d9bd9d-31af-4c75-b443-04377885242e",
                    "category": {
                        "id": "406f0389-df33-4a09-aed7-1fcb66f85321",
                        "name": "AC Service",
                        "slug": "ac-service",
                        "description": "Routine AC services.",
                        "image_url": "",
                        "display_order": 1,
                    },
                    "name": "AC General Service",
                    "slug": "ac-general-service",
                    "short_description": "Cleaning and inspection for split AC units.",
                    "base_price": "1499.00",
                    "advance_amount": "299.00",
                    "estimated_duration_minutes": 90,
                    "is_featured": True,
                    "description": "Includes filter cleaning, coil inspection, and drainage check.",
                },
                response_only=True,
            )
        ],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


@extend_schema(tags=["Admin - Categories"])
class AdminServiceCategoryViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = AdminServiceCategorySerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    lookup_field = "id"
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        return ServiceCategory.objects.all().order_by("display_order", "name")

    def perform_create(self, serializer):
        category = serializer.save()
        audit_event(
            action=AuditAction.CATEGORY_CREATED,
            actor=self.request.user,
            request=self.request,
            resource_type="service_category",
            resource_id=category.id,
            metadata={"slug": category.slug},
        )

    def perform_update(self, serializer):
        category = serializer.save()
        action = AuditAction.CATEGORY_UPDATED if category.is_active else AuditAction.CATEGORY_DEACTIVATED
        audit_event(
            action=action,
            actor=self.request.user,
            request=self.request,
            resource_type="service_category",
            resource_id=category.id,
            metadata={"slug": category.slug},
        )

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        category = self.get_object()
        if category.services.exists():
            category.is_active = False
            category.save(update_fields=["is_active", "updated_at"])
            audit_event(
                action=AuditAction.CATEGORY_DEACTIVATED,
                actor=request.user,
                request=request,
                resource_type="service_category",
                resource_id=category.id,
                metadata={"reason": "category_has_services"},
            )
            return Response(status=status.HTTP_204_NO_CONTENT)
        return super().destroy(request, *args, **kwargs)


@extend_schema(tags=["Admin - Catalogue"])
class AdminServiceViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = AdminServiceSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    lookup_field = "id"
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        return Service.objects.select_related("category").prefetch_related("images").all().order_by(
            "category__display_order",
            "display_order",
            "name",
        )

    def perform_create(self, serializer):
        service = serializer.save()
        audit_event(
            action=AuditAction.SERVICE_CREATED,
            actor=self.request.user,
            request=self.request,
            resource_type="service",
            resource_id=service.id,
            metadata={"slug": service.slug, "base_price": service.base_price},
        )

    def perform_update(self, serializer):
        previous = Service.objects.get(id=serializer.instance.id)
        service = serializer.save()
        action = AuditAction.SERVICE_UPDATED
        if service.base_price != previous.base_price or service.selling_price != previous.selling_price:
            action = AuditAction.SERVICE_PRICE_CHANGED
        elif service.cover_image != previous.cover_image:
            action = AuditAction.SERVICE_IMAGE_CHANGED
        elif not service.is_active:
            action = AuditAction.SERVICE_DEACTIVATED
        audit_event(
            action=action,
            actor=self.request.user,
            request=self.request,
            resource_type="service",
            resource_id=service.id,
            metadata={
                "slug": service.slug,
                "base_price": service.base_price,
                "selling_price": service.selling_price,
            },
        )

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        service = self.get_object()
        if Booking.objects.filter(service=service).exists():
            service.is_active = False
            service.save(update_fields=["is_active", "updated_at"])
            audit_event(
                action=AuditAction.SERVICE_DEACTIVATED,
                actor=request.user,
                request=request,
                resource_type="service",
                resource_id=service.id,
                metadata={"reason": "service_has_bookings"},
            )
            return Response(status=status.HTTP_204_NO_CONTENT)
        return super().destroy(request, *args, **kwargs)


@extend_schema(tags=["Admin - Service Images"])
class AdminServiceImageViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = ServiceImageSerializer
    parser_classes = [MultiPartParser, FormParser]
    lookup_url_kwarg = "image_id"
    lookup_field = "id"
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        return ServiceImage.objects.filter(service_id=self.kwargs["service_id"]).order_by("display_order", "created_at")

    def perform_create(self, serializer):
        service = generics.get_object_or_404(Service, id=self.kwargs["service_id"])
        image = serializer.save(service=service)
        audit_event(
            action=AuditAction.SERVICE_IMAGE_CHANGED,
            actor=self.request.user,
            request=self.request,
            resource_type="service",
            resource_id=service.id,
            metadata={"image_id": str(image.id), "operation": "created"},
        )

    def perform_update(self, serializer):
        image = serializer.save()
        audit_event(
            action=AuditAction.SERVICE_IMAGE_CHANGED,
            actor=self.request.user,
            request=self.request,
            resource_type="service",
            resource_id=image.service_id,
            metadata={"image_id": str(image.id), "operation": "updated"},
        )

    def perform_destroy(self, instance):
        service_id = instance.service_id
        image_id = instance.id
        instance.delete()
        audit_event(
            action=AuditAction.SERVICE_IMAGE_CHANGED,
            actor=self.request.user,
            request=self.request,
            resource_type="service",
            resource_id=service_id,
            metadata={"image_id": str(image_id), "operation": "deleted"},
        )
