from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.accounts.permissions import IsAdminRole
from apps.audit.models import AuditLog
from apps.audit.serializers import AuditLogSerializer


class AdminAuditLogViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = AuditLogSerializer
    lookup_field = "id"
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        queryset = AuditLog.objects.select_related("actor").order_by("-created_at")
        action = self.request.query_params.get("action")
        if action:
            queryset = queryset.filter(action=action)
        resource_type = self.request.query_params.get("resource_type")
        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)
        search = self.request.query_params.get("search")
        if search:
            term = search.strip()
            queryset = queryset.filter(
                Q(actor__phone_number__icontains=term)
                | Q(resource_id__icontains=term)
                | Q(request_id__icontains=term)
                | Q(ip_address__icontains=term)
            )
        return queryset

    @extend_schema(summary="List audit logs for admin", responses={status.HTTP_200_OK: AuditLogSerializer(many=True)})
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Get audit log for admin", responses={status.HTTP_200_OK: AuditLogSerializer})
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
