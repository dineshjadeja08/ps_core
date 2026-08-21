from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.reviews.models import Review
from apps.reviews.serializers import ReviewCreateSerializer, ReviewSerializer


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
