from django.conf import settings
from django.db.models import Avg, Q, Sum
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdminRole
from apps.audit.models import AuditAction
from apps.audit.services import audit_event
from apps.bookings.models import Booking, BookingStatus, PaymentStatus
from apps.operations.models import FAQ, HomepageBanner, Lead, LeadStatus, LeadStatusHistory
from apps.operations.serializers import (
    AdminReportSummarySerializer,
    AdminSettingsSerializer,
    FAQSerializer,
    HomepageBannerSerializer,
    LeadConvertSerializer,
    LeadSerializer,
)
from apps.payments.models import Payment, PaymentRecordStatus, PaymentType
from apps.reviews.models import Review


class AdminLeadViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = LeadSerializer
    lookup_field = "id"
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        queryset = Lead.objects.select_related("required_service", "assigned_staff", "converted_booking", "created_by").prefetch_related("status_history")
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        search = self.request.query_params.get("search")
        if search:
            term = search.strip()
            queryset = queryset.filter(Q(customer_name__icontains=term) | Q(primary_mobile__icontains=term))
        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        lead = serializer.save(created_by=self.request.user)
        LeadStatusHistory.objects.create(
            lead=lead,
            from_status="",
            to_status=lead.status,
            changed_by=self.request.user,
            notes="Lead created from admin API.",
        )
        audit_event(
            action=AuditAction.LEAD_CREATED,
            actor=self.request.user,
            request=self.request,
            resource_type="lead",
            resource_id=lead.id,
            metadata={"source": lead.source, "status": lead.status},
        )

    def perform_update(self, serializer):
        previous_status = self.get_object().status
        lead = serializer.save()
        action = AuditAction.LEAD_UPDATED
        metadata = {"status": lead.status}
        if previous_status != lead.status:
            LeadStatusHistory.objects.create(
                lead=lead,
                from_status=previous_status,
                to_status=lead.status,
                changed_by=self.request.user,
                notes=lead.internal_notes,
            )
            action = AuditAction.LEAD_STATUS_CHANGED
            metadata["from_status"] = previous_status
        audit_event(
            action=action,
            actor=self.request.user,
            request=self.request,
            resource_type="lead",
            resource_id=lead.id,
            metadata=metadata,
        )

    @extend_schema(
        summary="Convert lead by linking booking",
        request=LeadConvertSerializer,
        responses={status.HTTP_200_OK: LeadSerializer},
    )
    @action(detail=True, methods=["post"], url_path="convert")
    def convert(self, request, *args, **kwargs):
        lead = self.get_object()
        serializer = LeadConvertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = serializer.validated_data["booking_id"]
        previous_status = lead.status
        lead.status = LeadStatus.CONVERTED
        lead.converted_booking = booking
        lead.internal_notes = "\n".join(part for part in [lead.internal_notes, serializer.validated_data.get("notes", "")] if part)
        lead.save(update_fields=["status", "converted_booking", "internal_notes", "updated_at"])
        LeadStatusHistory.objects.create(
            lead=lead,
            from_status=previous_status,
            to_status=LeadStatus.CONVERTED,
            changed_by=request.user,
            notes=serializer.validated_data.get("notes", "") or "Lead converted.",
        )
        audit_event(
            action=AuditAction.LEAD_CONVERTED,
            actor=request.user,
            request=request,
            resource_type="lead",
            resource_id=lead.id,
            metadata={"booking_id": str(booking.id)},
        )
        return Response(LeadSerializer(lead, context={"request": request}).data)


class AdminFAQViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = FAQSerializer
    lookup_field = "id"
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        queryset = FAQ.objects.select_related("category", "service").order_by("display_order", "question")
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(question__icontains=search.strip())
        return queryset


class AdminHomepageBannerViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = HomepageBannerSerializer
    lookup_field = "id"
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        queryset = HomepageBanner.objects.order_by("placement", "display_order", "-created_at")
        placement = self.request.query_params.get("placement")
        if placement:
            queryset = queryset.filter(placement=placement)
        active = self.request.query_params.get("is_active")
        if active in {"true", "false"}:
            queryset = queryset.filter(is_active=active == "true")
        live = self.request.query_params.get("live")
        if live == "true":
            now = timezone.now()
            queryset = queryset.filter(
                is_active=True,
            ).filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now), Q(ends_at__isnull=True) | Q(ends_at__gte=now))
        return queryset

    def perform_create(self, serializer):
        banner = serializer.save()
        audit_event(
            action=AuditAction.BANNER_CREATED,
            actor=self.request.user,
            request=self.request,
            resource_type="homepage_banner",
            resource_id=banner.id,
            metadata={"placement": banner.placement, "is_active": banner.is_active},
        )

    def perform_update(self, serializer):
        banner = serializer.save()
        audit_event(
            action=AuditAction.BANNER_UPDATED,
            actor=self.request.user,
            request=self.request,
            resource_type="homepage_banner",
            resource_id=banner.id,
            metadata={"placement": banner.placement, "is_active": banner.is_active},
        )


class AdminReportsSummaryView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(summary="Get admin reports summary", responses={status.HTTP_200_OK: AdminReportSummarySerializer})
    def get(self, request):
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        bookings = Booking.objects.all()
        payments = Payment.objects.filter(status=PaymentRecordStatus.SUCCESS)
        if date_from:
            bookings = bookings.filter(created_at__date__gte=date_from)
            payments = payments.filter(created_at__date__gte=date_from)
        if date_to:
            bookings = bookings.filter(created_at__date__lte=date_to)
            payments = payments.filter(created_at__date__lte=date_to)

        revenue = payments.aggregate(total=Sum("amount"))["total"] or 0
        advance = payments.filter(payment_type=PaymentType.BOOKING_ADVANCE).aggregate(total=Sum("amount"))["total"] or 0
        balance = payments.filter(payment_type=PaymentType.BALANCE).aggregate(total=Sum("amount"))["total"] or 0
        refunds = payments.filter(payment_type=PaymentType.REFUND).aggregate(total=Sum("amount"))["total"] or 0
        payload = {
            "date_from": date_from,
            "date_to": date_to,
            "daily_bookings": bookings.count(),
            "completed_services": bookings.filter(booking_status=BookingStatus.COMPLETED).count(),
            "cancelled_bookings": bookings.filter(booking_status=BookingStatus.CANCELLED).count(),
            "payment_pending_bookings": bookings.filter(payment_status=PaymentStatus.UNPAID).count(),
            "revenue_collected": revenue,
            "advance_payments": advance,
            "balance_payments": balance,
            "refunds": refunds,
            "unassigned_bookings": bookings.filter(booking_status=BookingStatus.CONFIRMED, assigned_technician__isnull=True).count(),
            "average_rating": Review.objects.aggregate(value=Avg("rating"))["value"] or 0,
        }
        return Response(AdminReportSummarySerializer(payload).data)


class AdminSettingsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(summary="Get safe admin settings", responses={status.HTTP_200_OK: AdminSettingsSerializer})
    def get(self, request):
        payload = {
            "debug": settings.DEBUG,
            "allowed_hosts": list(settings.ALLOWED_HOSTS),
            "cors_allowed_origins": list(getattr(settings, "CORS_ALLOWED_ORIGINS", [])),
            "csrf_trusted_origins": list(getattr(settings, "CSRF_TRUSTED_ORIGINS", [])),
            "otp_provider": settings.OTP_AUTH_PROVIDER,
            "notification_provider": getattr(settings, "NOTIFICATION_PROVIDER", ""),
            "razorpay_configured": bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET),
            "msg91_configured": bool(settings.MSG91_AUTH_KEY and settings.MSG91_TEMPLATE_ID),
            "firebase_configured": bool(getattr(settings, "FIREBASE_CREDENTIALS_JSON", "")),
            "booking_require_balance_before_completion": settings.BOOKING_REQUIRE_BALANCE_BEFORE_COMPLETION,
        }
        return Response(AdminSettingsSerializer(payload).data)
