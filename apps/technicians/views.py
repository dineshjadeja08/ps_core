from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdminRole
from apps.audit.models import AuditAction
from apps.audit.services import audit_event
from apps.bookings.serializers import BookingSerializer
from apps.technicians.models import TechnicianProfile
from apps.technicians.serializers import AssignTechnicianRequestSerializer, TechnicianProfileSerializer
from apps.technicians.services import assign_technician


class AdminTechnicianListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = TechnicianProfileSerializer
    pagination_class = None

    def get_queryset(self):
        return (
            TechnicianProfile.objects.select_related("user")
            .prefetch_related("skills", "service_areas")
            .filter(is_active=True)
            .order_by("display_name")
        )

    @extend_schema(
        summary="List active technicians for admin",
        description="Returns active technician profiles for booking assignment.",
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
            },
        )
        return Response(BookingSerializer(booking).data)
