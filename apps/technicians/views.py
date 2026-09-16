from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdminRole, IsTechnicianRole
from apps.audit.models import AuditAction
from apps.audit.services import audit_event
from apps.bookings.models import Booking
from apps.bookings.serializers import AdminBookingSerializer, BookingOperationSerializer, BookingSerializer
from apps.bookings.services import complete_booking, mark_technician_en_route, start_booking
from apps.technicians.models import TechnicianProfile
from apps.technicians.serializers import (
    AssignTechnicianRequestSerializer,
    RemoveTechnicianAssignmentRequestSerializer,
    TechnicianProfileSerializer,
)
from apps.technicians.services import assign_technician, get_eligible_technicians, remove_technician_assignment


class TechnicianJobViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, IsTechnicianRole]
    serializer_class = AdminBookingSerializer
    lookup_field = "id"
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        return (
            Booking.objects.filter(assigned_technician=self.request.user)
            .select_related("customer", "customer__customer_profile", "service", "time_slot", "assigned_technician")
            .prefetch_related("status_history")
            .order_by("service_date", "time_slot__start_time")
        )

    def _operate(self, request, operation):
        serializer = BookingOperationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notes = serializer.validated_data.get("notes", "")
        booking = self.get_object()
        if operation == "en-route":
            booking = mark_technician_en_route(booking_id=booking.id, changed_by=request.user, notes=notes)
        elif operation == "start":
            booking = start_booking(booking_id=booking.id, changed_by=request.user, notes=notes)
        elif operation == "complete":
            booking = complete_booking(booking_id=booking.id, changed_by=request.user, notes=notes)
        return Response(AdminBookingSerializer(booking, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="en-route")
    def en_route(self, request, *args, **kwargs):
        return self._operate(request, "en-route")

    @action(detail=True, methods=["post"], url_path="start")
    def start(self, request, *args, **kwargs):
        return self._operate(request, "start")

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, *args, **kwargs):
        return self._operate(request, "complete")


class AdminTechnicianListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = TechnicianProfileSerializer
    pagination_class = None

    def get_queryset(self):
        queryset = (
            TechnicianProfile.objects.select_related("user")
            .prefetch_related("skills", "service_areas", "supported_services", "working_hours", "leaves")
            .filter(is_active=True)
            .order_by("display_name")
        )
        booking_id = self.request.query_params.get("booking_id")
        if not booking_id:
            return queryset
        try:
            booking = Booking.objects.select_related("address", "service", "time_slot", "time_slot__service_area").get(id=booking_id)
        except Booking.DoesNotExist:
            return TechnicianProfile.objects.none()
        eligible_ids = [technician.id for technician in get_eligible_technicians(booking)]
        return queryset.filter(id__in=eligible_ids)

    @extend_schema(
        summary="List active technicians for admin",
        description="Returns active technician profiles for booking assignment. Pass booking_id to list only eligible technicians.",
        parameters=[OpenApiParameter("booking_id", OpenApiTypes.UUID, OpenApiParameter.QUERY)],
        responses={status.HTTP_200_OK: TechnicianProfileSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class AssignTechnicianView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = AssignTechnicianRequestSerializer

    @extend_schema(
        summary="Assign technician to booking",
        description=(
            "Admin-only manual technician assignment. Records assignment history, supports reassignment, "
            "updates booking.assigned_technician, and moves booking status to TECHNICIAN_ASSIGNED."
        ),
        parameters=[OpenApiParameter("booking_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
        request=AssignTechnicianRequestSerializer,
        responses={status.HTTP_200_OK: BookingSerializer},
        examples=[
            OpenApiExample(
                "Assign technician request",
                value={"technician_id": "67d9bd9d-31af-4c75-b443-04377885242e", "notes": "Manual dispatch."},
                request_only=True,
            )
        ],
    )
    def post(self, request, booking_id):
        serializer = AssignTechnicianRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assignment = assign_technician(
            booking_id=booking_id,
            technician_id=serializer.validated_data["technician_id"],
            assigned_by=request.user,
            notes=serializer.validated_data.get("notes", ""),
            reason=serializer.validated_data.get("reason", ""),
        )
        booking = assignment.booking
        audit_event(
            action=AuditAction.TECHNICIAN_ASSIGN,
            actor=request.user,
            request=request,
            resource_type="booking",
            resource_id=booking.id,
            metadata={
                "technician_id": str(assignment.technician_id),
                "notes": serializer.validated_data.get("notes", ""),
                "reason": serializer.validated_data.get("reason", ""),
            },
        )
        return Response(BookingSerializer(booking).data)


class RemoveTechnicianAssignmentView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = RemoveTechnicianAssignmentRequestSerializer

    @extend_schema(
        summary="Remove technician assignment",
        description="Admin-only removal of the active technician assignment while preserving assignment history.",
        parameters=[OpenApiParameter("booking_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
        request=RemoveTechnicianAssignmentRequestSerializer,
        responses={status.HTTP_200_OK: BookingSerializer},
    )
    def post(self, request, booking_id):
        serializer = RemoveTechnicianAssignmentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = remove_technician_assignment(
            booking_id=booking_id,
            changed_by=request.user,
            notes=serializer.validated_data.get("notes", ""),
        )
        audit_event(
            action=AuditAction.TECHNICIAN_ASSIGNMENT_REMOVED,
            actor=request.user,
            request=request,
            resource_type="booking",
            resource_id=booking.id,
            metadata={"notes": serializer.validated_data.get("notes", "")},
        )
        return Response(BookingSerializer(booking).data)
