from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from django.db.models import Q
from rest_framework import viewsets
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.reviews.models import Review
from apps.accounts.permissions import IsAdminRole
from apps.audit.models import AuditAction
from apps.audit.services import audit_event
from apps.reviews.serializers import AdminReviewSerializer, ReviewCreateSerializer, ReviewSerializer


class BookingReviewCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Create booking review",
        description="Creates one review for an authenticated customer's completed booking.",
        request=ReviewCreateSerializer,
        responses={status.HTTP_201_CREATED: ReviewSerializer},
        examples=[
            OpenApiExample(
                "Review request",
                value={"rating": 5, "comment": "Technician was punctual and fixed the issue."},
                request_only=True,
            )
        ],
    )
    def post(self, request, booking_id):
        serializer = ReviewCreateSerializer(data=request.data, context={"request": request, "booking_id": booking_id})
        serializer.is_valid(raise_exception=True)
        review = serializer.save()
        return Response(ReviewSerializer(review).data, status=status.HTTP_201_CREATED)


class ServiceReviewListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ReviewSerializer

    @extend_schema(
        summary="List service reviews",
        description="Returns visible reviews for a service.",
        responses={status.HTTP_200_OK: ReviewSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return (
            Review.objects.select_related("booking", "customer", "technician")
            .filter(booking__service_id=self.kwargs["service_id"], is_visible=True)
            .order_by("-created_at")
        )


class AdminReviewViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = AdminReviewSerializer
    http_method_names = ["get", "patch", "head", "options"]
    lookup_field = "id"
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        queryset = Review.objects.select_related("booking", "booking__service", "customer", "technician").order_by("-created_at")
        visibility = self.request.query_params.get("is_visible")
        if visibility in {"true", "false"}:
            queryset = queryset.filter(is_visible=visibility == "true")
        search = self.request.query_params.get("search")
        if search:
            term = search.strip()
            queryset = queryset.filter(
                Q(comment__icontains=term)
                | Q(booking__booking_number__icontains=term)
                | Q(customer__phone_number__icontains=term)
                | Q(booking__service__name__icontains=term)
            )
        return queryset

    @extend_schema(summary="List reviews for admin", responses={status.HTTP_200_OK: AdminReviewSerializer(many=True)})
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Update review moderation fields", request=AdminReviewSerializer, responses={status.HTTP_200_OK: AdminReviewSerializer})
    def partial_update(self, request, *args, **kwargs):
        response = super().partial_update(request, *args, **kwargs)
        audit_event(
            action=AuditAction.REVIEW_UPDATED,
            actor=request.user,
            request=request,
            resource_type="review",
            resource_id=response.data["id"],
            metadata={"fields": list(request.data.keys())},
        )
        return response
