from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsAdminRole
from apps.audit.models import AuditAction
from apps.audit.services import audit_event
from apps.bookings.models import Booking
from apps.bookings.serializers import (
    BalanceCollectionSerializer,
    BookingCreateSerializer,
    BookingOperationSerializer,
    BookingRescheduleSerializer,
    BookingSerializer,
)
from apps.bookings.services import cancel_booking, complete_booking, start_booking


class AdminBookingViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = BookingSerializer
    lookup_field = "id"
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        queryset = (
            Booking.objects.select_related("customer", "service", "time_slot", "assigned_technician")
            .prefetch_related("status_history")
            .order_by("-created_at")
        )

        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(booking_status=status_filter)

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(booking_number__icontains=search.strip())

        return queryset

    @extend_schema(
        summary="List all bookings for admin",
        description="Returns all customer bookings for admin operations with optional status and booking number search.",
        responses={status.HTTP_200_OK: BookingSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Get any booking for admin",
        description="Returns one booking by id for admin operations.",
        responses={status.HTTP_200_OK: BookingSerializer},
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


class BookingViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    lookup_field = "id"
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        return (
            Booking.objects.select_related("service", "time_slot")
            .prefetch_related("status_history")
            .filter(customer=self.request.user)
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        if self.action == "create":
            return BookingCreateSerializer
        return BookingSerializer

    @extend_schema(
        summary="Create booking",
        description=(
            "Creates a PENDING_PAYMENT booking for the authenticated customer. "
            "The backend validates service, address ownership, service area, slot availability, "
            "locks the slot transactionally, snapshots address and price values, and writes status history."
        ),
        request=BookingCreateSerializer,
        responses={status.HTTP_201_CREATED: BookingSerializer},
        examples=[
            OpenApiExample(
                "Create booking request",
                value={
                    "service_id": "67d9bd9d-31af-4c75-b443-04377885242e",
                    "address_id": "406f0389-df33-4a09-aed7-1fcb66f85321",
                    "slot_id": "d4206031-f805-4303-9d8a-e7d465e06794",
                    "problem_description": "AC is not cooling properly.",
                    "customer_notes": "Please call before arriving.",
                },
                request_only=True,
            )
        ],
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()
        return Response(BookingSerializer(booking).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="List customer bookings",
        description="Returns bookings belonging to the authenticated customer.",
        responses={status.HTTP_200_OK: BookingSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Get customer booking",
        description="Returns one booking belonging to the authenticated customer.",
        responses={status.HTTP_200_OK: BookingSerializer},
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        summary="Cancel customer booking",
        description="Cancels an authenticated customer's booking when policy and status allow it.",
        request=BookingOperationSerializer,
        responses={status.HTTP_200_OK: BookingSerializer},
    )
    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, *args, **kwargs):
        booking = self.get_object()
        serializer = BookingOperationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = cancel_booking(
            booking_id=booking.id,
            changed_by=request.user,
            notes=serializer.validated_data.get("notes", ""),
            actor="customer",
        )
        return Response(BookingSerializer(booking).data)

    @extend_schema(
        summary="Reschedule customer booking",
        description="Moves an authenticated customer's booking to another available slot when policy allows it.",
        request=BookingRescheduleSerializer,
        responses={status.HTTP_200_OK: BookingSerializer},
    )
    @action(detail=True, methods=["post"], url_path="reschedule")
    def reschedule(self, request, *args, **kwargs):
        booking = self.get_object()
        serializer = BookingRescheduleSerializer(
            data=request.data,
            context={"request": request, "booking_id": booking.id},
        )
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()
        return Response(BookingSerializer(booking).data)


class AdminBookingOperationView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]
    operation = None

    @extend_schema(
        summary="Run admin booking operation",
        request=BookingOperationSerializer,
        responses={status.HTTP_200_OK: BookingSerializer},
    )
    def post(self, request, booking_id):
        serializer = BookingOperationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notes = serializer.validated_data.get("notes", "")
        if self.operation == "start":
            booking = start_booking(booking_id=booking_id, changed_by=request.user, notes=notes)
            action = AuditAction.ADMIN_BOOKING_START
        elif self.operation == "complete":
            booking = complete_booking(booking_id=booking_id, changed_by=request.user, notes=notes)
            action = AuditAction.ADMIN_BOOKING_COMPLETE
        elif self.operation == "cancel":
            booking = cancel_booking(booking_id=booking_id, changed_by=request.user, notes=notes, actor="admin")
            action = AuditAction.ADMIN_BOOKING_CANCEL
        else:
            raise AssertionError("Unsupported booking operation.")
        audit_event(
            action=action,
            actor=request.user,
            request=request,
            resource_type="booking",
            resource_id=booking.id,
            metadata={"notes": notes},
        )
        return Response(BookingSerializer(booking).data)


class AdminBookingBalanceCollectionView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(
        summary="Record offline booking balance",
        request=BalanceCollectionSerializer,
        responses={status.HTTP_200_OK: BookingSerializer},
    )
    def post(self, request, booking_id):
        serializer = BalanceCollectionSerializer(
            data=request.data,
            context={"request": request, "booking_id": booking_id},
        )
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()
        audit_event(
            action=AuditAction.ADMIN_RECORD_BALANCE,
            actor=request.user,
            request=request,
            resource_type="booking",
            resource_id=booking.id,
            metadata=serializer.validated_data,
        )
        return Response(BookingSerializer(booking).data)
