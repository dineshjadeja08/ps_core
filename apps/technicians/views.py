from copy import copy
from pathlib import Path

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponse
from django.db import transaction
from django.db.models import Avg, Count, F, Q
from django.utils import timezone
from django.utils.text import get_valid_filename
from rest_framework.exceptions import ValidationError
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User, UserRole
from apps.accounts.permissions import IsAdminRole, IsTechnicianRole
from apps.audit.models import AuditAction
from apps.audit.services import audit_event
from apps.bookings.models import Booking, BookingStatus
from apps.bookings.serializers import AdminBookingSerializer, BalanceCollectionSerializer, BookingActivitySerializer, BookingOperationSerializer, BookingSerializer
from apps.catalogue.models import Service
from apps.locations.models import ServiceArea
from apps.bookings.services import accept_job, complete_booking, mark_technician_arrived, mark_technician_en_route, start_booking, start_job_with_otp
from apps.reviews.models import Review
from apps.technicians.models import (
    JobPhoto,
    PrivateTechnicianDocument,
    PrivateTechnicianDocumentStatus,
    TechnicianCompanyUser,
    TechnicianDocument,
    TechnicianDocumentType,
    TechnicianLeave,
    TechnicianProfile,
    TechnicianSkill,
)
from apps.technicians.private_documents import delete_private_document, read_private_document, store_private_document
from apps.technicians.serializers import (
    AssignTechnicianRequestSerializer,
    RemoveTechnicianAssignmentRequestSerializer,
    TechnicianLeaveRequestSerializer,
    TechnicianLeaveReviewSerializer,
    TechnicianLeaveSerializer,
    AdminTechnicianProfileSerializer,
    AdminTechnicianDetailSerializer,
    AdminTechnicianWriteSerializer,
    TechnicianCompanyUserCreateSerializer,
    TechnicianCompanyUserSerializer,
    TechnicianPerformanceSerializer,
    TechnicianProfileSerializer,
    TechnicianReviewSerializer,
    StartJobSerializer,
    JobPhotoSerializer,
    JobPhotoUploadSerializer,
    TechnicianEarningsSerializer,
    KycDecisionSerializer,
    TechnicianDocumentSerializer,
    TechnicianDocumentUploadSerializer,
    TechnicianProfileUpdateSerializer,
    TechnicianSkillSerializer,
    PrivateTechnicianDocumentSerializer,
    PrivateTechnicianDocumentUploadSerializer,
    PrivateTechnicianDocumentVerificationSerializer,
)
from apps.technicians.services import (
    TECHNICIAN_BUSY_STATUSES,
    assign_technician,
    decide_kyc,
    ensure_kyc_editable,
    get_technician_earnings,
    get_technician_eligibility_errors,
    get_technician_performance,
    remove_technician_assignment,
    submit_kyc,
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
        profile = _own_technician_profile(self.request.user)
        queryset = (
            Booking.objects.filter(
                assigned_technician=profile.user,
                assigned_technician__technician_profile__is_active=True,
                assigned_technician__technician_profile__employment_status="ACTIVE",
                assigned_technician__technician_profile__background_verification_status="VERIFIED",
            ).exclude(assigned_technician__technician_profile__availability_status="SUSPENDED")
            .select_related("customer", "customer__customer_profile", "service", "time_slot", "assigned_technician__technician_profile")
            .prefetch_related("status_history")
            .order_by("service_date", "time_slot__start_time")
        )
        job_status = self.request.query_params.get("job_status")
        if job_status == "active":
            queryset = queryset.filter(booking_status__in=TECHNICIAN_BUSY_STATUSES)
        elif job_status == "history":
            queryset = queryset.exclude(booking_status__in=TECHNICIAN_BUSY_STATUSES).order_by("-service_date", "-created_at")
        return queryset

    def _operate(self, request, operation):
        serializer = BookingOperationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notes = serializer.validated_data.get("notes", "")
        booking = self.get_object()
        # Partner flow: Accept → On the way → Arrived → Start (customer OTP) → Complete.
        if operation == "accept":
            booking = accept_job(booking_id=booking.id, changed_by=request.user)
        elif operation == "en-route":
            booking = mark_technician_en_route(booking_id=booking.id, changed_by=request.user, notes=notes)
        elif operation == "arrived":
            booking = mark_technician_arrived(booking_id=booking.id, changed_by=request.user, notes=notes)
        elif operation == "start":
            if booking.booking_status == BookingStatus.IN_PROGRESS:
                return Response(AdminBookingSerializer(booking, context={"request": request}).data)
            if booking.booking_status != BookingStatus.TECHNICIAN_ARRIVED:
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
        membership = TechnicianCompanyUser.objects.filter(
            user=user, is_active=True, technician__is_active=True,
        ).select_related("technician__user").first()
        profile = membership.technician if membership else None
    if profile is None:
        raise NotFound("No technician profile is linked to this account.")
    return profile


@extend_schema(tags=["Technician"])
class TechnicianSelfProfileView(APIView):
    permission_classes = [IsAuthenticated, IsTechnicianRole]

    @extend_schema(summary="Get my technician profile", responses={status.HTTP_200_OK: TechnicianProfileSerializer})
    def get(self, request):
        return Response(TechnicianProfileSerializer(_own_technician_profile(request.user), context={"request": request}).data)

    @extend_schema(
        summary="Update my KYC details",
        description="Partners fill these in during sign-up. Allowed only while KYC is pending or rejected.",
        request=TechnicianProfileUpdateSerializer,
        responses={status.HTTP_200_OK: TechnicianProfileSerializer},
    )
    def patch(self, request):
        profile = _own_technician_profile(request.user)
        if profile.user_id != request.user.id:
            raise ValidationError("Only the primary partner account can edit company KYC details.")
        ensure_kyc_editable(profile)
        serializer = TechnicianProfileUpdateSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            profile = serializer.save()
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict) from exc
        return Response(TechnicianProfileSerializer(_own_technician_profile(request.user), context={"request": request}).data)


@extend_schema(tags=["Technician"])
class TechnicianSkillListView(generics.ListAPIView):
    """Services a partner can choose to offer during sign-up."""

    permission_classes = [IsAuthenticated, IsTechnicianRole]
    serializer_class = TechnicianSkillSerializer
    pagination_class = None
    queryset = TechnicianSkill.objects.filter(is_active=True).order_by("name")


@extend_schema(tags=["Technician"])
class TechnicianDocumentListView(APIView):
    permission_classes = [IsAuthenticated, IsTechnicianRole]

    @extend_schema(summary="List my KYC documents", responses={status.HTTP_200_OK: TechnicianDocumentSerializer(many=True)})
    def get(self, request):
        profile = _own_technician_profile(request.user)
        return Response(TechnicianDocumentSerializer(profile.documents.all(), many=True, context={"request": request}).data)

    @extend_schema(
        summary="Upload a KYC document",
        description="multipart/form-data with doc_type and file (jpg, png, webp, heic or pdf, up to 8 MB). Uploading Aadhaar, PAN or photo again replaces the previous one.",
        request={"multipart/form-data": TechnicianDocumentUploadSerializer},
        responses={status.HTTP_201_CREATED: TechnicianDocumentSerializer},
    )
    def post(self, request):
        profile = _own_technician_profile(request.user)
        if profile.user_id != request.user.id:
            raise ValidationError("Only the primary partner account can upload company KYC documents.")
        ensure_kyc_editable(profile)
        serializer = TechnicianDocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = TechnicianDocument(technician=profile, **serializer.validated_data)
        try:
            document.full_clean()
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict) from exc
        with transaction.atomic():
            if document.doc_type != TechnicianDocumentType.CERTIFICATE:
                profile.documents.filter(doc_type=document.doc_type).delete()
            document.save()
        return Response(TechnicianDocumentSerializer(document, context={"request": request}).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Technician"])
class TechnicianDocumentDetailView(APIView):
    permission_classes = [IsAuthenticated, IsTechnicianRole]

    @extend_schema(summary="Remove a KYC document", responses={status.HTTP_204_NO_CONTENT: None})
    def delete(self, request, document_id):
        profile = _own_technician_profile(request.user)
        if profile.user_id != request.user.id:
            raise ValidationError("Only the primary partner account can manage company KYC documents.")
        ensure_kyc_editable(profile)
        deleted, _ = profile.documents.filter(id=document_id).delete()
        if not deleted:
            raise NotFound("Document not found.")
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Technician"])
class TechnicianKycSubmitView(APIView):
    permission_classes = [IsAuthenticated, IsTechnicianRole]

    @extend_schema(
        summary="Submit my KYC for review",
        description="Requires name, city, pincode, at least one service, and Aadhaar front/back, PAN and photo. Lists what is missing otherwise.",
        request=None,
        responses={status.HTTP_200_OK: TechnicianProfileSerializer},
    )
    def post(self, request):
        profile = _own_technician_profile(request.user)
        if profile.user_id != request.user.id:
            raise ValidationError("Only the primary partner account can submit company KYC.")
        profile = submit_kyc(profile)
        return Response(TechnicianProfileSerializer(profile, context={"request": request}).data)


@extend_schema(tags=["Admin - Technicians"])
class AdminTechnicianKycView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def _profile(self, technician_id):
        return generics.get_object_or_404(TechnicianProfile.objects.prefetch_related("skills", "service_areas", "supported_services__category"), id=technician_id)

    @extend_schema(summary="Get a technician's KYC details and documents", responses={status.HTTP_200_OK: OpenApiTypes.OBJECT})
    def get(self, request, technician_id):
        profile = self._profile(technician_id)
        return Response({
            "profile": TechnicianProfileSerializer(profile, context={"request": request}).data,
            "documents": TechnicianDocumentSerializer(profile.documents.all(), many=True, context={"request": request}).data,
        })

    @extend_schema(summary="Approve or reject a technician's KYC", request=KycDecisionSerializer, responses={status.HTTP_200_OK: TechnicianProfileSerializer})
    def post(self, request, technician_id):
        serializer = KycDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        approve = serializer.validated_data["decision"] == "APPROVE"
        profile = decide_kyc(profile=self._profile(technician_id), approve=approve, note=serializer.validated_data.get("note", ""))
        audit_event(
            action=AuditAction.TECHNICIAN_KYC_APPROVED if approve else AuditAction.TECHNICIAN_KYC_REJECTED,
            actor=request.user,
            request=request,
            resource_type="technician",
            resource_id=profile.id,
            metadata={"note": profile.verification_note},
        )
        return Response(TechnicianProfileSerializer(profile, context={"request": request}).data)


@extend_schema(tags=["Technician"])
class TechnicianSelfReviewListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsTechnicianRole]
    serializer_class = TechnicianReviewSerializer

    def get_queryset(self):
        profile = _own_technician_profile(self.request.user)
        return (
            Review.objects.filter(technician=profile.user, is_visible=True)
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
        profile = _own_technician_profile(self.request.user)
        return TechnicianLeave.objects.filter(technician=profile).select_related("technician", "approved_by").order_by("-start_at")

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
        profile = _own_technician_profile(request.user)
        report = get_technician_performance(user=profile.user, period=request.query_params.get("period", "overall"))
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
        profile = _own_technician_profile(request.user)
        report = get_technician_earnings(user=profile.user, period=request.query_params.get("period", "overall"))
        return Response(TechnicianEarningsSerializer(report).data)


@extend_schema(tags=["Admin - Bookings"])
class AdminJobPhotoListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(summary="List completion photos for a booking", responses={status.HTTP_200_OK: JobPhotoSerializer(many=True)})
    def get(self, request, booking_id):
        photos = JobPhoto.objects.filter(booking_id=booking_id)
        return Response(JobPhotoSerializer(photos, many=True, context={"request": request}).data)



class AdminTechnicianQueryMixin:
    permission_classes = [IsAuthenticated, IsAdminRole]
    include_inactive = False

    def get_serializer_class(self):
        return AdminTechnicianProfileSerializer if self.request.method in {"GET", "HEAD"} else AdminTechnicianWriteSerializer

    def get_queryset(self):
        today = timezone.localdate()
        month_start = today.replace(day=1)
        year_start = today.replace(month=1, day=1)
        queryset = (
            TechnicianProfile.objects.select_related("user", "sales_person_assigned")
            .prefetch_related("skills", "service_areas", "supported_services", "working_hours", "leaves")
            .annotate(
                active_job_count=Count("user__assigned_bookings", distinct=True, filter=Q(user__assigned_bookings__booking_status__in=TECHNICIAN_BUSY_STATUSES)),
                completed_jobs=Count("user__assigned_bookings", distinct=True, filter=Q(user__assigned_bookings__booking_status__in=[BookingStatus.COMPLETED, BookingStatus.CLOSED])),
                monthly_job_count=Count(
                    "user__assigned_bookings",
                    distinct=True,
                    filter=Q(
                        user__assigned_bookings__booking_status__in=[BookingStatus.COMPLETED, BookingStatus.CLOSED],
                        user__assigned_bookings__completed_at__date__gte=month_start,
                        user__assigned_bookings__completed_at__date__lte=today,
                    ),
                ),
                yearly_job_count=Count(
                    "user__assigned_bookings",
                    distinct=True,
                    filter=Q(
                        user__assigned_bookings__booking_status__in=[BookingStatus.COMPLETED, BookingStatus.CLOSED],
                        user__assigned_bookings__completed_at__date__gte=year_start,
                        user__assigned_bookings__completed_at__date__lte=today,
                    ),
                ),
                cancelled_jobs=Count("user__assigned_bookings", distinct=True, filter=Q(user__assigned_bookings__booking_status=BookingStatus.CANCELLED)),
                approved_rating=Avg("user__technician_reviews__rating", filter=Q(user__technician_reviews__is_visible=True)),
                approved_review_count=Count("user__technician_reviews", distinct=True, filter=Q(user__technician_reviews__is_visible=True)),
            )
            .order_by("display_name")
        )
        if not self.include_inactive and self.request.query_params.get("include_inactive") != "true":
            queryset = queryset.filter(is_active=True)
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(Q(display_name__icontains=search) | Q(phone__icontains=search) | Q(employee_code__icontains=search))
        for param, field in (("service_id", "supported_services__id"), ("area_id", "service_areas__id")):
            value = self.request.query_params.get(param)
            if value:
                try:
                    queryset = queryset.filter(**{field: value})
                except (ValueError, DjangoValidationError):
                    raise ValidationError({param: "Use a valid ID."})
        availability = self.request.query_params.get("availability_status")
        if availability:
            queryset = queryset.filter(availability_status=availability)
        active = self.request.query_params.get("is_active")
        if active in {"true", "false"}:
            queryset = queryset.filter(is_active=active == "true")
        verification = self.request.query_params.get("verification", "").upper()
        if verification:
            queryset = queryset.filter(background_verification_status=verification)
        booking_id = self.request.query_params.get("booking_id")
        if not booking_id:
            return queryset
        try:
            booking = Booking.objects.select_related("address", "service", "time_slot", "time_slot__service_area").get(id=booking_id)
        except Booking.DoesNotExist:
            raise ValidationError({"booking_id": "Booking was not found."})
        except (ValueError, DjangoValidationError):
            raise ValidationError({"booking_id": "Use a valid booking ID."})
        technicians = list(queryset)
        for technician in technicians:
            technician.eligibility_errors = get_technician_eligibility_errors(technician, booking)
        if self.request.query_params.get("include_ineligible") == "true":
            return technicians
        return [technician for technician in technicians if not technician.eligibility_errors]

    def record_change(self, serializer, created=False):
        previous = None if created else {
            "verification": serializer.instance.background_verification_status,
            "availability": serializer.instance.availability_status,
        }
        with transaction.atomic():
            technician = serializer.save()
            action = AuditAction.TECHNICIAN_CREATED if created else AuditAction.TECHNICIAN_UPDATED
            if previous and previous["verification"] != technician.background_verification_status:
                action = AuditAction.TECHNICIAN_VERIFICATION_CHANGED
            elif previous and previous["availability"] != technician.availability_status:
                action = AuditAction.TECHNICIAN_AVAILABILITY_CHANGED
            audit_event(
                action=action, actor=self.request.user, request=self.request,
                resource_type="technician", resource_id=technician.id,
                metadata={"fields": list(serializer.validated_data), "verification": technician.background_verification_status,
                          "availability": technician.availability_status, "is_active": technician.is_active},
            )


class AdminTechnicianListView(AdminTechnicianQueryMixin, generics.ListCreateAPIView):
    pagination_class = None

    def perform_create(self, serializer):
        self.record_change(serializer, created=True)

    @extend_schema(
        summary="List technicians for admin",
        description="Active technicians by default. include_inactive=true includes inactive profiles. Pass booking_id for eligibility and include_ineligible=true for reasons.",
        parameters=[
            OpenApiParameter("booking_id", OpenApiTypes.UUID, OpenApiParameter.QUERY),
            OpenApiParameter("verification", str, OpenApiParameter.QUERY, enum=["PENDING", "UNDER_REVIEW", "VERIFIED", "REJECTED", "SUSPENDED"]),
        ],
        responses={status.HTTP_200_OK: AdminTechnicianProfileSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class AdminTechnicianDetailView(AdminTechnicianQueryMixin, generics.RetrieveUpdateAPIView):
    include_inactive = True

    def get_serializer_class(self):
        if self.request.method in {"GET", "HEAD"}:
            return AdminTechnicianDetailSerializer
        return AdminTechnicianWriteSerializer

    def perform_update(self, serializer):
        self.record_change(serializer)


class AdminTechnicianDocumentsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]
    parser_classes = [MultiPartParser, FormParser]

    def get_technician(self, pk):
        return generics.get_object_or_404(TechnicianProfile, pk=pk)

    @extend_schema(summary="List private technician documents", responses=PrivateTechnicianDocumentSerializer(many=True))
    def get(self, request, pk):
        technician = self.get_technician(pk)
        documents = technician.private_documents.select_related("uploaded_by", "verified_by").all()
        return Response(PrivateTechnicianDocumentSerializer(documents, many=True, context={"request": request}).data)

    @extend_schema(summary="Upload or replace a private technician document", request=PrivateTechnicianDocumentUploadSerializer, responses=PrivateTechnicianDocumentSerializer)
    def post(self, request, pk):
        technician = self.get_technician(pk)
        serializer = PrivateTechnicianDocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded = serializer.validated_data["file"]
        try:
            backend, storage_id, resource_type = store_private_document(uploaded)
        except Exception as exc:
            from rest_framework.exceptions import APIException

            raise APIException("Private document storage is unavailable. Check server storage configuration.") from exc
        existing = PrivateTechnicianDocument.objects.filter(
            technician=technician, document_type=serializer.validated_data["document_type"],
        ).first()
        try:
            with transaction.atomic():
                if existing:
                    old_document = copy(existing)
                    existing.storage_public_id = storage_id
                    existing.storage_backend = backend
                    existing.storage_resource_type = resource_type
                    existing.original_name = get_valid_filename(Path(uploaded.name).name)[:255]
                    existing.content_type = uploaded.content_type
                    existing.file_size = uploaded.size
                    existing.verification_status = PrivateTechnicianDocumentStatus.PENDING
                    existing.verification_note = ""
                    existing.uploaded_by = request.user
                    existing.verified_by = None
                    existing.verified_at = None
                    existing.save()
                    document = existing
                else:
                    old_document = None
                    document = PrivateTechnicianDocument.objects.create(
                        technician=technician,
                        document_type=serializer.validated_data["document_type"],
                        storage_public_id=storage_id,
                        storage_backend=backend,
                        storage_resource_type=resource_type,
                        original_name=get_valid_filename(Path(uploaded.name).name)[:255],
                        content_type=uploaded.content_type,
                        file_size=uploaded.size,
                        uploaded_by=request.user,
                    )
        except Exception:
            from apps.technicians.private_documents import delete_private_document
            from apps.technicians.models import PrivateTechnicianDocument as DocumentModel

            orphan = DocumentModel(storage_public_id=storage_id, storage_backend=backend, storage_resource_type=resource_type)
            try:
                delete_private_document(orphan)
            except Exception:
                pass
            raise
        if old_document:
            try:
                delete_private_document(old_document)
            except Exception:
                pass
        audit_event(
            action=AuditAction.TECHNICIAN_DOCUMENT_UPLOADED, actor=request.user, request=request,
            resource_type="technician_document", resource_id=document.id,
            metadata={"technician_id": str(technician.id), "document_type": document.document_type, "replaced": bool(old_document)},
        )
        return Response(PrivateTechnicianDocumentSerializer(document, context={"request": request}).data, status=status.HTTP_201_CREATED)


class AdminTechnicianDocumentContentView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(summary="Preview/download a private technician document", responses={200: OpenApiTypes.BINARY})
    def get(self, request, pk, document_id):
        document = generics.get_object_or_404(
            PrivateTechnicianDocument.objects.select_related("technician"), pk=document_id, technician_id=pk,
        )
        try:
            content = read_private_document(document)
        except Exception as exc:
            from rest_framework.exceptions import APIException

            raise APIException("Private document could not be retrieved from storage.") from exc
        disposition = "inline" if request.query_params.get("download") != "true" else "attachment"
        response = HttpResponse(content, content_type=document.content_type)
        response["Content-Disposition"] = f'{disposition}; filename="{document.original_name.replace(chr(34), "")}"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return response


class AdminTechnicianDocumentDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = PrivateTechnicianDocumentSerializer

    @extend_schema(summary="Verify or reject a technician document", request=PrivateTechnicianDocumentVerificationSerializer, responses=PrivateTechnicianDocumentSerializer)
    def patch(self, request, pk, document_id):
        document = generics.get_object_or_404(PrivateTechnicianDocument, pk=document_id, technician_id=pk)
        serializer = PrivateTechnicianDocumentVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document.verification_status = serializer.validated_data["verification_status"]
        document.verification_note = serializer.validated_data.get("verification_note", "").strip()
        document.verified_by = request.user
        document.verified_at = timezone.now()
        document.save(update_fields=["verification_status", "verification_note", "verified_by", "verified_at", "updated_at"])
        audit_event(
            action=AuditAction.TECHNICIAN_DOCUMENT_VERIFIED, actor=request.user, request=request,
            resource_type="technician_document", resource_id=document.id,
            metadata={"technician_id": str(pk), "document_type": document.document_type, "status": document.verification_status},
        )
        return Response(PrivateTechnicianDocumentSerializer(document, context={"request": request}).data)

    @extend_schema(summary="Remove a technician document", responses={204: None})
    def post(self, request, pk, document_id):
        document = generics.get_object_or_404(PrivateTechnicianDocument, pk=document_id, technician_id=pk)
        delete_private_document(document)
        document.delete()
        audit_event(
            action=AuditAction.TECHNICIAN_DOCUMENT_DELETED, actor=request.user, request=request,
            resource_type="technician_document", resource_id=document_id,
            metadata={"technician_id": str(pk), "deleted": True},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminTechnicianCompanyUsersView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get_technician(self, pk):
        return generics.get_object_or_404(TechnicianProfile, pk=pk)

    @extend_schema(summary="List company users for one technician", responses=TechnicianCompanyUserSerializer(many=True))
    def get(self, request, pk):
        technician = self.get_technician(pk)
        memberships = technician.company_users.select_related("user").all()
        return Response(TechnicianCompanyUserSerializer(memberships, many=True).data)

    @extend_schema(summary="Add a company user by existing account phone number", request=TechnicianCompanyUserCreateSerializer, responses=TechnicianCompanyUserSerializer)
    def post(self, request, pk):
        technician = self.get_technician(pk)
        serializer = TechnicianCompanyUserCreateSerializer(data=request.data, context={"technician": technician})
        serializer.is_valid(raise_exception=True)
        membership = serializer.save()
        audit_event(
            action=AuditAction.TECHNICIAN_COMPANY_USER_CHANGED, actor=request.user, request=request,
            resource_type="technician_company_user", resource_id=membership.id,
            metadata={"technician_id": str(pk), "role": membership.role, "added": True},
        )
        return Response(TechnicianCompanyUserSerializer(membership).data, status=status.HTTP_201_CREATED)


class AdminTechnicianCompanyUserDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = TechnicianCompanyUserSerializer

    def get_membership(self, pk, user_id):
        return generics.get_object_or_404(
            TechnicianCompanyUser.objects.select_related("user"), pk=user_id, technician_id=pk,
        )

    @extend_schema(summary="Update a company user's role or active status", request=OpenApiTypes.OBJECT, responses=TechnicianCompanyUserSerializer)
    def patch(self, request, pk, user_id):
        membership = self.get_membership(pk, user_id)
        role = request.data.get("role", membership.role)
        active = request.data.get("is_active", membership.is_active)
        if role not in {"OWNER", "MANAGER", "STAFF"} or not isinstance(active, bool):
            raise ValidationError({"detail": "Provide a valid role and boolean is_active value."})
        membership.role = role
        membership.is_active = active
        membership.save(update_fields=["role", "is_active", "updated_at"])
        audit_event(
            action=AuditAction.TECHNICIAN_COMPANY_USER_CHANGED, actor=request.user, request=request,
            resource_type="technician_company_user", resource_id=membership.id,
            metadata={"technician_id": str(pk), "role": role, "is_active": active},
        )
        return Response(TechnicianCompanyUserSerializer(membership).data)

    @extend_schema(summary="Remove a company user from this technician", responses={204: None})
    def post(self, request, pk, user_id):
        membership = self.get_membership(pk, user_id)
        membership.delete()
        audit_event(
            action=AuditAction.TECHNICIAN_COMPANY_USER_CHANGED, actor=request.user, request=request,
            resource_type="technician_company_user", resource_id=user_id,
            metadata={"technician_id": str(pk), "removed": True},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminTechnicianOptionsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(summary="List technician coverage options", responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response({
            "skills": list(TechnicianSkill.objects.values("id", "name", "is_active")),
            "services": list(Service.objects.values("id", "name", "is_active", category_name=F("category__name"))),
            "areas": list(ServiceArea.objects.values("id", "name", "city", "postal_code", "is_active")),
            "sales_people": [
                {
                    "id": str(user.id),
                    "name": " ".join(filter(None, [user.first_name, user.last_name])).strip() or user.phone_number,
                    "phone_number": user.phone_number,
                }
                for user in User.objects.filter(
                    is_staff=True, is_active=True, role__in=[UserRole.ADMIN, UserRole.SUPER_ADMIN],
                ).order_by("first_name", "last_name", "phone_number")
            ],
        })


class AdminTechnicianJobsView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = AdminBookingSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Booking.objects.none()
        technician = generics.get_object_or_404(TechnicianProfile, pk=self.kwargs["pk"])
        queryset = Booking.objects.filter(assigned_technician=technician.user).select_related(
            "customer", "customer__customer_profile", "service", "time_slot", "assigned_technician",
        ).prefetch_related("status_history").order_by("-service_date", "time_slot__start_time")
        if self.request.query_params.get("active") == "true":
            queryset = queryset.filter(booking_status__in=TECHNICIAN_BUSY_STATUSES).order_by("service_date", "time_slot__start_time")
        return queryset


class AdminTechnicianActivityView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(summary="List recent technician activity", responses=BookingActivitySerializer(many=True))
    def get(self, request, pk):
        from apps.technicians.activities import technician_activities

        technician = generics.get_object_or_404(TechnicianProfile, pk=pk)
        return Response(BookingActivitySerializer(technician_activities(technician), many=True).data)


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
