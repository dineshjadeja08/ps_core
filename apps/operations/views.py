import csv
from datetime import timedelta

from django.conf import settings
from django.http import HttpResponse
from django.db.models import Avg, Q, Sum
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import CustomerProfile, User, UserRole
from apps.accounts.permissions import IsAdminRole
from apps.audit.models import AuditAction
from apps.audit.services import audit_event
from apps.bookings.models import Booking, BookingStatus, PaymentStatus
from apps.notifications.models import Notification, NotificationChannel, NotificationEvent, NotificationStatus
from apps.notifications.services import send_notification
from apps.operations.models import ACTIVE_LEAD_STATUSES, FAQ, HomepageBanner, Lead, LeadFunnelStatus, LeadStatus, LeadStatusHistory
from apps.operations.serializers import (
    AdminDashboardSummarySerializer,
    AdminGlobalSearchSerializer,
    AdminReportSummarySerializer,
    AdminSettingsSerializer,
    FAQSerializer,
    LeadActivitySerializer,
    HomepageBannerSerializer,
    LeadContactSerializer,
    LeadConvertSerializer,
    LeadManualPaymentSerializer,
    LeadPaymentLinkSerializer,
    LeadReminderSerializer,
    LeadScheduleSerializer,
    LeadSerializer,
    LeadSummarySerializer,
)
from apps.operations.services import convert_lead_to_work_order, record_lead_contact, record_manual_lead_payment, send_lead_payment_link
from apps.payments.models import Payment, PaymentRecordStatus, PaymentType
from apps.reviews.models import Review
from apps.technicians.models import TechnicianAvailabilityStatus, TechnicianProfile, TechnicianVerificationStatus


class PublicFAQListView(ListAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = FAQSerializer
    pagination_class = None

    def get_queryset(self):
        queryset = FAQ.objects.filter(is_active=True).order_by("display_order", "question")
        service_id = self.request.query_params.get("service_id")
        category_id = self.request.query_params.get("category_id")
        if service_id:
            queryset = queryset.filter(service_id=service_id)
        elif category_id:
            queryset = queryset.filter(category_id=category_id, service__isnull=True)
        else:
            queryset = queryset.filter(category__isnull=True, service__isnull=True)
        return queryset


class AdminLeadViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = LeadSerializer
    lookup_field = "id"
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        queryset = Lead.objects.select_related(
            "customer",
            "required_service",
            "assigned_staff",
            "converted_booking",
            "pending_booking",
            "created_by",
        ).prefetch_related("status_history", "activities")
        status_filter = self.request.query_params.get("status")
        if status_filter == "OPEN":
            queryset = queryset.filter(status__in=ACTIVE_LEAD_STATUSES)
        elif status_filter:
            queryset = queryset.filter(status=status_filter)
        funnel_status = self.request.query_params.get("funnel_status")
        if funnel_status:
            queryset = queryset.filter(funnel_status=funnel_status)
        payment_status = self.request.query_params.get("payment_status")
        if payment_status:
            queryset = queryset.filter(payment_status=payment_status)
        source = self.request.query_params.get("source")
        if source:
            queryset = queryset.filter(source=source)
        assigned_to = self.request.query_params.get("assigned_to")
        if assigned_to:
            queryset = queryset.filter(assigned_staff_id=assigned_to)
        service = self.request.query_params.get("service")
        if service:
            queryset = queryset.filter(required_service_id=service)
        service_search = self.request.query_params.get("service_search", "").strip()
        if service_search:
            queryset = queryset.filter(required_service__name__icontains=service_search)
        city = self.request.query_params.get("city", "").strip()
        if city:
            queryset = queryset.filter(city__icontains=city)
        mobile = self.request.query_params.get("mobile", "").strip()
        if mobile:
            queryset = queryset.filter(primary_mobile__icontains=mobile)
        request_id = self.request.query_params.get("request_id", "").strip()
        if request_id:
            queryset = queryset.filter(
                Q(id__icontains=request_id)
                | Q(converted_booking__booking_number__icontains=request_id)
                | Q(pending_booking__booking_number__icontains=request_id)
            )
        created_from = self.request.query_params.get("created_from")
        if created_from:
            queryset = queryset.filter(created_at__date__gte=created_from)
        created_to = self.request.query_params.get("created_to")
        if created_to:
            queryset = queryset.filter(created_at__date__lte=created_to)
        follow_up_date = self.request.query_params.get("follow_up_date")
        if follow_up_date:
            queryset = queryset.filter(follow_up_at__date=follow_up_date)
        search = self.request.query_params.get("search")
        if search:
            term = search.strip()
            queryset = queryset.filter(
                Q(customer_name__icontains=term)
                | Q(primary_mobile__icontains=term)
                | Q(id__icontains=term)
                | Q(converted_booking__booking_number__icontains=term)
                | Q(pending_booking__booking_number__icontains=term)
                | Q(required_service__name__icontains=term)
            )
        ordering = self.request.query_params.get("ordering", "-last_activity_at")
        allowed_ordering = {
            "created_at",
            "-created_at",
            "last_activity_at",
            "-last_activity_at",
            "follow_up_at",
            "-follow_up_at",
            "customer_name",
            "-customer_name",
        }
        if ordering not in allowed_ordering:
            ordering = "-last_activity_at"
        return queryset.order_by(ordering)

    def perform_create(self, serializer):
        mobile = serializer.validated_data["primary_mobile"]
        customer, created = User.objects.get_or_create(
            phone_number=mobile,
            defaults={"role": UserRole.CUSTOMER, "is_active": True, "is_verified": True},
        )
        if created:
            customer.set_unusable_password()
            customer.save(update_fields=["password", "updated_at"])
        CustomerProfile.objects.get_or_create(
            user=customer,
            defaults={"display_name": serializer.validated_data["customer_name"]},
        )
        lead = serializer.save(created_by=self.request.user, customer=customer)
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
    @action(detail=True, methods=["post"], url_path="convert-to-booking")
    def convert(self, request, *args, **kwargs):
        lead = self.get_object()
        serializer = LeadConvertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = serializer.validated_data.get("booking_id")
        lead = convert_lead_to_work_order(
            lead=lead,
            performed_by=request.user,
            booking=booking,
            notes=serializer.validated_data.get("notes", ""),
        )
        audit_event(
            action=AuditAction.LEAD_CONVERTED,
            actor=request.user,
            request=request,
            resource_type="lead",
            resource_id=lead.id,
            metadata={"booking_id": str(lead.converted_booking_id)},
        )
        return Response(LeadSerializer(lead, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="convert")
    def convert_legacy(self, request, *args, **kwargs):
        return self.convert(request, *args, **kwargs)

    @extend_schema(summary="Get lead summary", responses={status.HTTP_200_OK: LeadSummarySerializer})
    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        today = timezone.localdate()
        queryset = self.filter_queryset(self.get_queryset())
        payload = {
            "all_leads": queryset.count(),
            "visited": queryset.filter(funnel_status=LeadFunnelStatus.VISITED).count(),
            "cart_added": queryset.filter(funnel_status=LeadFunnelStatus.CART_ADDED).count(),
            "unpaid": queryset.filter(funnel_status=LeadFunnelStatus.UNPAID).count(),
            "paid": queryset.filter(funnel_status=LeadFunnelStatus.PAID).count(),
            "booked": queryset.filter(funnel_status=LeadFunnelStatus.BOOKED).count(),
            "follow_ups_due_today": queryset.filter(follow_up_at__date__lte=today).exclude(
                funnel_status__in=[LeadFunnelStatus.PAID, LeadFunnelStatus.BOOKED, LeadFunnelStatus.CANCELLED, LeadFunnelStatus.LOST]
            ).count(),
        }
        return Response(LeadSummarySerializer(payload).data)

    @extend_schema(summary="List lead activities", responses={status.HTTP_200_OK: LeadActivitySerializer(many=True)})
    @action(detail=True, methods=["get"], url_path="activities")
    def activities(self, request, *args, **kwargs):
        lead = self.get_object()
        return Response(LeadActivitySerializer(lead.activities.all(), many=True).data)

    @extend_schema(summary="Schedule a lead", request=LeadScheduleSerializer, responses={status.HTTP_200_OK: LeadSerializer})
    @action(detail=True, methods=["post"], url_path="schedule")
    def schedule(self, request, *args, **kwargs):
        lead = self.get_object()
        serializer = LeadScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["preferred_date"] < timezone.localdate():
            return Response({"detail": "Schedule date cannot be in the past."}, status=status.HTTP_400_BAD_REQUEST)
        lead.preferred_date = serializer.validated_data["preferred_date"]
        lead.preferred_slot = serializer.validated_data["preferred_slot"]
        lead.last_activity_at = timezone.now()
        lead.save(update_fields=["preferred_date", "preferred_slot", "last_activity_at", "updated_at"])
        return Response(LeadSerializer(lead, context={"request": request}).data)

    @extend_schema(summary="Send a customer reminder", request=LeadReminderSerializer, responses={status.HTTP_200_OK: LeadSerializer})
    @action(detail=True, methods=["post"], url_path="send-reminder")
    def send_reminder(self, request, *args, **kwargs):
        lead = self.get_object()
        serializer = LeadReminderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notification = Notification.objects.create(
            recipient=lead.customer,
            booking=lead.converted_booking or lead.pending_booking,
            event=NotificationEvent.BOOKING_RECEIVED,
            channel=serializer.validated_data["channel"],
            title="Purple Squad service reminder",
            message=f"Hello {lead.customer_name}, Purple Squad is following up on your {lead.required_service.name if lead.required_service else 'service'} request.",
            payload={"lead_id": str(lead.id), "mobile": lead.primary_mobile},
        )
        send_notification(notification)
        return Response(LeadSerializer(lead, context={"request": request}).data)

    @extend_schema(summary="Send payment link for unpaid lead", request=LeadPaymentLinkSerializer, responses={status.HTTP_200_OK: LeadSerializer})
    @action(detail=True, methods=["post"], url_path="send-payment-link")
    def send_payment_link(self, request, *args, **kwargs):
        lead = self.get_object()
        serializer = LeadPaymentLinkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lead, created = send_lead_payment_link(
            lead=lead,
            performed_by=request.user,
            request=request,
            channel=serializer.validated_data["channel"],
            payment_scope=serializer.validated_data["payment_scope"],
        )
        response = LeadSerializer(lead, context={"request": request}).data
        response["payment_link_created"] = created
        return Response(response)

    @extend_schema(summary="Record lead contact", request=LeadContactSerializer, responses={status.HTTP_200_OK: LeadSerializer})
    @action(detail=True, methods=["post"], url_path="record-contact")
    def record_contact(self, request, *args, **kwargs):
        lead = self.get_object()
        serializer = LeadContactSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get("next_follow_up_at"):
            lead.follow_up_at = serializer.validated_data["next_follow_up_at"]
            lead.save(update_fields=["follow_up_at", "updated_at"])
        lead = record_lead_contact(
            lead=lead,
            performed_by=request.user,
            note=serializer.validated_data["note"],
            request=request,
        )
        return Response(LeadSerializer(lead, context={"request": request}).data)

    @extend_schema(summary="Record audited manual lead payment", request=LeadManualPaymentSerializer, responses={status.HTTP_200_OK: LeadSerializer})
    @action(detail=True, methods=["post"], url_path="record-manual-payment")
    def record_manual_payment(self, request, *args, **kwargs):
        lead = self.get_object()
        serializer = LeadManualPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lead, _payment = record_manual_lead_payment(
            lead=lead,
            performed_by=request.user,
            amount=serializer.validated_data["amount"],
            method=serializer.validated_data["method"],
            reference=serializer.validated_data.get("reference", ""),
            payment_date=serializer.validated_data["payment_date"],
            note=serializer.validated_data.get("note", ""),
            request=request,
        )
        return Response(LeadSerializer(lead, context={"request": request}).data)

    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="purple-squad-leads.csv"'
        writer = csv.writer(response)
        writer.writerow(["Lead ID", "Customer", "Mobile", "Service", "Source", "Funnel status", "Payment status", "Amount", "Last activity", "Follow-up"])
        for lead in self.filter_queryset(self.get_queryset())[:1000]:
            writer.writerow(
                [
                    lead.id,
                    lead.customer_name,
                    lead.primary_mobile,
                    lead.required_service.name if lead.required_service else "",
                    lead.source,
                    lead.funnel_status,
                    lead.payment_status,
                    lead.quoted_amount or "",
                    lead.last_activity_at,
                    lead.follow_up_at or "",
                ]
            )
        return response


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


class AdminDashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(summary="Get admin dashboard summary", responses={status.HTTP_200_OK: AdminDashboardSummarySerializer})
    def get(self, request):
        today = timezone.localdate()
        now = timezone.now()
        upcoming_until = today + timedelta(days=7)
        active_booking_statuses = {
            BookingStatus.CONFIRMED,
            BookingStatus.TECHNICIAN_ASSIGNED,
            BookingStatus.TECHNICIAN_EN_ROUTE,
            BookingStatus.IN_PROGRESS,
        }
        upcoming_excluded_statuses = {
            BookingStatus.COMPLETED,
            BookingStatus.CLOSED,
            BookingStatus.CANCELLED,
            BookingStatus.REFUNDED,
        }

        successful_payments_today = Payment.objects.filter(
            status=PaymentRecordStatus.SUCCESS,
            paid_at__date=today,
            payment_type__in=[PaymentType.BOOKING_ADVANCE, PaymentType.BALANCE],
        )
        daily_gmv = successful_payments_today.aggregate(total=Sum("amount"))["total"] or 0
        active_bookings = Booking.objects.filter(booking_status__in=active_booking_statuses)
        unassigned_bookings = active_bookings.filter(assigned_technician__isnull=True)
        active_leads = Lead.objects.filter(status__in=ACTIVE_LEAD_STATUSES)

        payload = {
            "daily_gmv": daily_gmv,
            "active_bookings_count": active_bookings.count(),
            "available_technicians_count": TechnicianProfile.objects.filter(
                user__is_active=True,
                is_active=True,
                is_available=True,
                availability_status=TechnicianAvailabilityStatus.AVAILABLE,
                background_verification_status=TechnicianVerificationStatus.VERIFIED,
            ).count(),
            "open_unassigned_leads_count": active_leads.filter(assigned_staff__isnull=True).count(),
            "leads_today": Lead.objects.filter(created_at__date=today).count(),
            "follow_ups_due": active_leads.filter(follow_up_at__lte=now).count(),
            "bookings_today": Booking.objects.filter(created_at__date=today).count(),
            "confirmed_bookings": Booking.objects.filter(booking_status=BookingStatus.CONFIRMED).count(),
            "payment_pending_bookings": Booking.objects.filter(payment_status=PaymentStatus.UNPAID).count(),
            "revenue_today": daily_gmv,
            "unassigned_bookings": unassigned_bookings.count(),
            "upcoming_services": Booking.objects.filter(
                service_date__gte=today,
                service_date__lte=upcoming_until,
            )
            .exclude(booking_status__in=upcoming_excluded_statuses)
            .count(),
            "failed_notifications": Notification.objects.filter(status=NotificationStatus.FAILED).count(),
        }
        return Response(AdminDashboardSummarySerializer(payload).data)


class AdminGlobalSearchView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(summary="Search admin records", responses={status.HTTP_200_OK: AdminGlobalSearchSerializer})
    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if len(query) < 2:
            return Response({"query": query, "results": []})

        results = []
        work_orders = (
            Booking.objects.filter(payments__status=PaymentRecordStatus.SUCCESS)
            .filter(
                Q(booking_number__icontains=query)
                | Q(customer__phone_number__icontains=query)
                | Q(customer__first_name__icontains=query)
                | Q(customer__last_name__icontains=query)
                | Q(customer__customer_profile__display_name__icontains=query)
            )
            .select_related("customer", "customer__customer_profile", "service")
            .distinct()[:8]
        )
        for booking in work_orders:
            profile = getattr(booking.customer, "customer_profile", None)
            name = (getattr(profile, "display_name", "") or "").strip()
            name = name or " ".join(filter(None, [booking.customer.first_name, booking.customer.last_name])).strip()
            results.append(
                {
                    "type": "WORK_ORDER",
                    "id": str(booking.id),
                    "title": booking.booking_number,
                    "subtitle": f"{name or booking.customer.phone_number} · {booking.service.name}",
                    "url": f"/admin/work-orders/{booking.id}",
                }
            )

        leads = (
            Lead.objects.filter(
                Q(primary_mobile__icontains=query)
                | Q(customer_name__icontains=query)
                | Q(converted_booking__booking_number__icontains=query)
                | Q(pending_booking__booking_number__icontains=query)
            )
            .select_related("required_service")[:8]
        )
        for lead in leads:
            results.append(
                {
                    "type": "LEAD",
                    "id": str(lead.id),
                    "title": lead.customer_name or lead.primary_mobile,
                    "subtitle": f"{lead.primary_mobile} · {lead.required_service.name if lead.required_service else 'General enquiry'}",
                    "url": f"/admin/leads/{lead.id}",
                }
            )

        customers = (
            User.objects.filter(role=UserRole.CUSTOMER)
            .filter(
                Q(phone_number__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(customer_profile__display_name__icontains=query)
            )
            .select_related("customer_profile")[:8]
        )
        for customer in customers:
            profile = getattr(customer, "customer_profile", None)
            name = (getattr(profile, "display_name", "") or "").strip()
            name = name or " ".join(filter(None, [customer.first_name, customer.last_name])).strip()
            results.append(
                {
                    "type": "CUSTOMER",
                    "id": str(customer.id),
                    "title": name or customer.phone_number,
                    "subtitle": customer.phone_number,
                    "url": f"/admin/customers?customer={customer.id}",
                }
            )
        return Response(AdminGlobalSearchSerializer({"query": query, "results": results[:20]}).data)


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
            "completed_services": bookings.filter(booking_status__in=[BookingStatus.COMPLETED, BookingStatus.CLOSED]).count(),
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
            "msg91_configured": bool(
                settings.MSG91_AUTH_KEY
                and settings.MSG91_TEMPLATE_ID
                and settings.MSG91_WHATSAPP_INTEGRATED_NUMBER
                and settings.MSG91_WHATSAPP_TEMPLATE_NAME
                and settings.MSG91_WHATSAPP_TEMPLATE_NAMESPACE
            ),
            "firebase_configured": bool(getattr(settings, "FIREBASE_CREDENTIALS_JSON", "")),
            "cloudinary_media_enabled": bool(getattr(settings, "USE_CLOUDINARY_MEDIA", False)),
            "cloudinary_media_configured": bool(
                getattr(settings, "CLOUDINARY_URL", "")
                or (
                    getattr(settings, "CLOUDINARY_CLOUD_NAME", "")
                    and getattr(settings, "CLOUDINARY_API_KEY", "")
                    and getattr(settings, "CLOUDINARY_API_SECRET", "")
                )
            ),
            "booking_require_balance_before_completion": settings.BOOKING_REQUIRE_BALANCE_BEFORE_COMPLETION,
        }
        return Response(AdminSettingsSerializer(payload).data)
