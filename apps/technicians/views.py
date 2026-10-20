from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdminRole, IsTechnicianRole
from apps.audit.models import AuditAction
from apps.audit.services import audit_event
from apps.bookings.models import Booking
from apps.bookings.serializers import AdminBookingSerializer, BalanceCollectionSerializer, BookingOperationSerializer, BookingSerializer
from apps.bookings.models import BookingStatus
from apps.bookings.services import accept_job, complete_booking, mark_technician_arrived, mark_technician_en_route, start_job_with_otp
from apps.reviews.models import Review
from apps.technicians.models import JobPhoto, TechnicianLeave, TechnicianProfile
from apps.technicians.serializers import (
    AssignTechnicianRequestSerializer,
    RemoveTechnicianAssignmentRequestSerializer,
    TechnicianLeaveRequestSerializer,
    TechnicianLeaveReviewSerializer,
    TechnicianLeaveSerializer,
    TechnicianPerformanceSerializer,
    TechnicianProfileSerializer,
    TechnicianReviewSerializer,
    StartJobSerializer,
    JobPhotoSerializer,
    JobPhotoUploadSerializer,
    TechnicianEarningsSerializer,
)
from apps.technicians.services import (
    assign_technician,
    get_eligible_technicians,
    get_technician_earnings,
    get_technician_performance,
    remove_technician_assignment,
)


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
            .select_related("customer", "customer__customer_profile", "service", "time_slot", "assigned_technician__technician_profile")
            .prefetch_related("status_history")
            .order_by("service_date", "time_slot__start_time")
        )

    def _operate(self, request, operation):
        serializer = BookingOperationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notes = serializer.validated_data.get("notes", "")
        booking = self.get_object()
        # Partner flow: Accept → On the way → Arrived → Start (customer OTP) → Complete.
        if operation == "accept":
            booking = accept_job(booking_id=booking.id, changed_by=request.user)
        elif operation == "en-route":
            if booking.accepted_at is None:
                raise ValidationError("Accept the job before you start travelling.")
            booking = mark_technician_en_route(booking_id=booking.id, changed_by=request.user, notes=notes)
        elif operation == "arrived":
            booking = mark_technician_arrived(booking_id=booking.id, changed_by=request.user)
        elif operation == "start":
            if booking.booking_status != BookingStatus.TECHNICIAN_EN_ROUTE or booking.arrived_at is None:
                raise ValidationError("Mark that you have arrived before starting the job.")
            otp = StartJobSerializer(data=request.data)
            otp.is_valid(raise_exception=True)
            booking = start_job_with_otp(booking_id=booking.id, changed_by=request.user, otp=otp.validated_data["otp"], notes=notes)
        elif operation == "complete":
            booking = complete_booking(booking_id=booking.id, changed_by=request.user, notes=notes)
        return Response(AdminBookingSerializer(booking, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="accept")
    def accept(self, request, *args, **kwargs):
        return self._operate(request, "accept")

    @action(detail=True, methods=["post"], url_path="en-route")
    def en_route(self, request, *args, **kwargs):
        return self._operate(request, "en-route")

    @action(detail=True, methods=["post"], url_path="arrived")
    def arrived(self, request, *args, **kwargs):
        return self._operate(request, "arrived")

    @extend_schema(summary="Start job with the customer's service OTP", request=StartJobSerializer, responses={status.HTTP_200_OK: AdminBookingSerializer})
    @action(detail=True, methods=["post"], url_path="start")
    def start(self, request, *args, **kwargs):
        return self._operate(request, "start")

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, *args, **kwargs):
        return self._operate(request, "complete")

    @extend_schema(summary="List completion photos for my job", responses={status.HTTP_200_OK: JobPhotoSerializer(many=True)})
    @action(detail=True, methods=["get"], url_path="photos")
    def photos(self, request, *args, **kwargs):
        booking = self.get_object()
        return Response(JobPhotoSerializer(booking.job_photos.all(), many=True, context={"request": request}).data)

    @extend_schema(
        summary="Upload a completion photo or receipt",
        description="multipart/form-data with kind (BEFORE, AFTER, RECEIPT) and file (jpg, png, webp, heic or pdf, up to 8 MB). Only while the job is in progress.",
        request={"multipart/form-data": JobPhotoUploadSerializer},
        responses={status.HTTP_201_CREATED: JobPhotoSerializer},
    )
    @photos.mapping.post
    def upload_photo(self, request, *args, **kwargs):
        booking = self.get_object()
        if booking.booking_status != BookingStatus.IN_PROGRESS:
            raise ValidationError("Photos can only be added while the job is in progress.")
        serializer = JobPhotoUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        photo = JobPhoto(booking=booking, uploaded_by=request.user, **serializer.validated_data)
        try:
            photo.full_clean()
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict) from exc
        photo.save()
        return Response(JobPhotoSerializer(photo, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @extend_schema(summary="Remove a completion photo", responses={status.HTTP_204_NO_CONTENT: None})
    @action(detail=True, methods=["delete"], url_path=r"photos/(?P<photo_id>[0-9a-f-]{36})")
    def delete_photo(self, request, photo_id, *args, **kwargs):
        booking = self.get_object()
        if booking.booking_status != BookingStatus.IN_PROGRESS:
            raise ValidationError("Photos can only be removed while the job is in progress.")
        deleted, _ = booking.job_photos.filter(id=photo_id).delete()
        if not deleted:
            raise NotFound("Photo not found.")
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="Record balance collected from the customer",
        description="Records cash/UPI/card the technician collected on site. Required before completing a job with a balance due.",
        request=BalanceCollectionSerializer,
        responses={status.HTTP_200_OK: AdminBookingSerializer},
    )
    @action(detail=True, methods=["post"], url_path="collect-balance")
    def collect_balance(self, request, *args, **kwargs):
        booking = self.get_object()
        serializer = BalanceCollectionSerializer(data=request.data, context={"request": request, "booking_id": booking.id})
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()
        audit_event(
            action=AuditAction.TECHNICIAN_RECORD_BALANCE,
            actor=request.user,
            request=request,
            resource_type="booking",
            resource_id=booking.id,
            metadata=serializer.validated_data,
        )
        return Response(AdminBookingSerializer(booking, context={"request": request}).data)



def _own_technician_profile(user):
    profile = TechnicianProfile.objects.filter(user=user).prefetch_related("skills", "service_areas", "supported_services__category").first()
    if profile is None:
        raise NotFound("No technician profile is linked to this account.")
    return profile


@extend_schema(tags=["Technician"])
class TechnicianSelfProfileView(APIView):
    permission_classes = [IsAuthenticated, IsTechnicianRole]

    @extend_schema(summary="Get my technician profile", responses={status.HTTP_200_OK: TechnicianProfileSerializer})
    def get(self, request):
        return Response(TechnicianProfileSerializer(_own_technician_profile(request.user), context={"request": request}).data)


@extend_schema(tags=["Technician"])
class TechnicianSelfReviewListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsTechnicianRole]
    serializer_class = TechnicianReviewSerializer

    def get_queryset(self):
        return (
            Review.objects.filter(technician=self.request.user, is_visible=True)
            .select_related("booking__service", "customer__customer_profile")
            .order_by("-created_at")
        )

    @extend_schema(summary="List reviews customers left for me")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


@extend_schema(tags=["Technician"])
class TechnicianSelfLeaveViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsTechnicianRole]
    serializer_class = TechnicianLeaveSerializer

    def get_queryset(self):
        return TechnicianLeave.objects.filter(technician__user=self.request.user).select_related("technician", "approved_by").order_by("-start_at")

    @extend_schema(summary="List my leave requests")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Request leave",
        description="Creates a pending leave request. An admin approves or rejects it.",
        request=TechnicianLeaveRequestSerializer,
        responses={status.HTTP_201_CREATED: TechnicianLeaveSerializer},
    )
    def create(self, request, *args, **kwargs):
        serializer = TechnicianLeaveRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = _own_technician_profile(request.user)
        data = serializer.validated_data
        overlapping = TechnicianLeave.objects.filter(
            technician=profile, is_active=True, start_at__lt=data["end_at"], end_at__gt=data["start_at"]
        ).exists()
        if overlapping:
            raise ValidationError({"start_at": "You already have a leave request for these dates."})
        leave = TechnicianLeave.objects.create(technician=profile, **data)
        audit_event(
            action=AuditAction.TECHNICIAN_LEAVE_CREATED,
            actor=request.user,
            request=request,
            resource_type="technician_leave",
            resource_id=leave.id,
            metadata={"technician_id": str(profile.id), "self_service": True},
        )
        return Response(TechnicianLeaveSerializer(leave, context={"request": request}).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Technician"])
class TechnicianSelfPerformanceView(APIView):
    permission_classes = [IsAuthenticated, IsTechnicianRole]

    @extend_schema(
        summary="Get my performance report",
        parameters=[OpenApiParameter("period", str, OpenApiParameter.QUERY, description="'overall' (default) or YYYY-MM")],
        responses={status.HTTP_200_OK: TechnicianPerformanceSerializer},
    )
    def get(self, request):
        report = get_technician_performance(user=request.user, period=request.query_params.get("period", "overall"))
        return Response(TechnicianPerformanceSerializer(report).data)


@extend_schema(tags=["Technician"])
class TechnicianSelfEarningsView(APIView):
    permission_classes = [IsAuthenticated, IsTechnicianRole]

    @extend_schema(
        summary="Get my completed-job earnings",
        description="Job values of completed jobs and how they were paid. Commission and payouts are not included yet.",
        parameters=[OpenApiParameter("period", str, OpenApiParameter.QUERY, description="'overall' (default) or YYYY-MM")],
        responses={status.HTTP_200_OK: TechnicianEarningsSerializer},
    )
    def get(self, request):
        report = get_technician_earnings(user=request.user, period=request.query_params.get("period", "overall"))
        return Response(TechnicianEarningsSerializer(report).data)


@extend_schema(tags=["Admin - Bookings"])
class AdminJobPhotoListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(summary="List completion photos for a booking", responses={status.HTTP_200_OK: JobPhotoSerializer(many=True)})
    def get(self, request, booking_id):
        photos = JobPhoto.objects.filter(booking_id=booking_id)
        return Response(JobPhotoSerializer(photos, many=True, context={"request": request}).data)


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


@extend_schema(tags=["Admin - Technician Leaves"])
class AdminTechnicianLeaveViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = TechnicianLeaveSerializer
    lookup_field = "id"
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        queryset = TechnicianLeave.objects.select_related("technician", "approved_by").order_by("-start_at")
        technician_id = self.request.query_params.get("technician")
        if technician_id:
            queryset = queryset.filter(technician_id=technician_id)
        status_filter = self.request.query_params.get("status", "").upper()
        if status_filter == "PENDING":
            queryset = queryset.filter(is_active=True, approved_by__isnull=True)
        elif status_filter == "APPROVED":
            queryset = queryset.filter(is_active=True, approved_by__isnull=False)
        elif status_filter == "REJECTED":
            queryset = queryset.filter(is_active=False)
        return queryset

    @extend_schema(
        summary="List technician leave requests",
        parameters=[
            OpenApiParameter("technician", OpenApiTypes.UUID, OpenApiParameter.QUERY),
            OpenApiParameter("status", str, OpenApiParameter.QUERY, enum=["PENDING", "APPROVED", "REJECTED"]),
        ],
        responses={status.HTTP_200_OK: TechnicianLeaveSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Approve technician leave",
        request=TechnicianLeaveReviewSerializer,
        responses={status.HTTP_200_OK: TechnicianLeaveSerializer},
    )
    @action(detail=True, methods=["post"])
    def approve(self, request, *args, **kwargs):
        serializer = TechnicianLeaveReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            leave = generics.get_object_or_404(
                TechnicianLeave.objects.select_for_update().select_related("technician", "approved_by"),
                id=kwargs["id"],
            )
            leave.approved_by = request.user
            leave.review_note = serializer.validated_data.get("note", "")
            leave.is_active = True
            leave.save(update_fields=["approved_by", "review_note", "is_active", "updated_at"])
            audit_event(
                action=AuditAction.TECHNICIAN_LEAVE_APPROVED,
                actor=request.user,
                request=request,
                resource_type="technician_leave",
                resource_id=leave.id,
                metadata={"technician_id": str(leave.technician_id), "note": leave.review_note},
            )
        return Response(TechnicianLeaveSerializer(leave, context={"request": request}).data)

    @extend_schema(
        summary="Reject technician leave",
        request=TechnicianLeaveReviewSerializer,
        responses={status.HTTP_200_OK: TechnicianLeaveSerializer},
    )
    @action(detail=True, methods=["post"])
    def reject(self, request, *args, **kwargs):
        serializer = TechnicianLeaveReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            leave = generics.get_object_or_404(
                TechnicianLeave.objects.select_for_update().select_related("technician", "approved_by"),
                id=kwargs["id"],
            )
            leave.approved_by = None
            leave.review_note = serializer.validated_data.get("note", "")
            leave.is_active = False
            leave.save(update_fields=["approved_by", "review_note", "is_active", "updated_at"])
            audit_event(
                action=AuditAction.TECHNICIAN_LEAVE_REJECTED,
                actor=request.user,
                request=request,
                resource_type="technician_leave",
                resource_id=leave.id,
                metadata={"technician_id": str(leave.technician_id), "note": leave.review_note},
            )
        return Response(TechnicianLeaveSerializer(leave, context={"request": request}).data)


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
