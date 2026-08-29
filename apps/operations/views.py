from django.utils import timezone
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsAdminRole
from apps.audit.models import AuditAction
from apps.audit.services import audit_event
from apps.operations.models import FAQ, HomepageBanner, Lead, LeadStatus, LeadStatusHistory
from apps.operations.serializers import FAQSerializer, HomepageBannerSerializer, LeadConvertSerializer, LeadSerializer


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
