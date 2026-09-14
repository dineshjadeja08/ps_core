from rest_framework.routers import SimpleRouter

from django.urls import path

from apps.notifications.views import AdminNotificationViewSet, msg91_delivery_webhook

router = SimpleRouter()
router.register("admin/notifications", AdminNotificationViewSet, basename="admin-notification")

urlpatterns = [
    path("notifications/webhooks/msg91/", msg91_delivery_webhook, name="msg91-notification-webhook"),
] + router.urls
