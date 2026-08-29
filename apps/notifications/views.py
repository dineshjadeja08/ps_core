from django.utils import timezone
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsAdminRole
from apps.notifications.models import Notification, NotificationStatus
from apps.notifications.serializers import NotificationActionSerializer, NotificationSerializer
from apps.notifications.services import send_notification


class AdminNotificationViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = NotificationSerializer
    lookup_field = "id"
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        queryset = Notification.objects.select_related("recipient", "booking").order_by("-created_at")
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        event = self.request.query_params.get("event")
        if event:
            queryset = queryset.filter(event=event)
        channel = self.request.query_params.get("channel")
        if channel:
            queryset = queryset.filter(channel=channel)
        search = self.request.query_params.get("search")
        if search:
            term = search.strip()
            queryset = queryset.filter(Q(title__icontains=term) | Q(message__icontains=term) | Q(booking__booking_number__icontains=term))
        return queryset

    @extend_schema(summary="List notifications for admin", responses={status.HTTP_200_OK: NotificationSerializer(many=True)})
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Create manual notification", request=NotificationSerializer, responses={status.HTTP_201_CREATED: NotificationSerializer})
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @extend_schema(summary="Retry failed notification", request=NotificationActionSerializer, responses={status.HTTP_200_OK: NotificationSerializer})
    @action(detail=True, methods=["post"])
    def retry(self, request, *args, **kwargs):
        notification = self.get_object()
        serializer = NotificationActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if notification.status != NotificationStatus.FAILED:
            return Response(
                {"error": {"code": "NOTIFICATION_NOT_FAILED", "message": "Only failed notifications can be retried.", "details": {}}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        notification = send_notification(notification)
        return Response(NotificationSerializer(notification).data)

    @extend_schema(summary="Cancel queued notification", request=NotificationActionSerializer, responses={status.HTTP_200_OK: NotificationSerializer})
    @action(detail=True, methods=["post"])
    def cancel(self, request, *args, **kwargs):
        notification = self.get_object()
        serializer = NotificationActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if notification.status != NotificationStatus.QUEUED:
            return Response(
                {"error": {"code": "NOTIFICATION_NOT_QUEUED", "message": "Only queued notifications can be cancelled.", "details": {}}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        notification.status = NotificationStatus.CANCELLED
        notification.error_message = serializer.validated_data.get("reason", "")
        notification.save(update_fields=["status", "error_message", "updated_at"])
        return Response(NotificationSerializer(notification).data)

    @extend_schema(summary="Send queued notification", request=NotificationActionSerializer, responses={status.HTTP_200_OK: NotificationSerializer})
    @action(detail=True, methods=["post"])
    def send(self, request, *args, **kwargs):
        notification = self.get_object()
        serializer = NotificationActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if notification.status not in {NotificationStatus.QUEUED, NotificationStatus.FAILED}:
            return Response(
                {"error": {"code": "NOTIFICATION_NOT_SENDABLE", "message": "Notification cannot be sent from its current status.", "details": {}}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        notification.updated_at = timezone.now()
        notification = send_notification(notification)
        return Response(NotificationSerializer(notification).data)
