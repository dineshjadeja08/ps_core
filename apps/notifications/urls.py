from rest_framework.routers import SimpleRouter

from django.urls import path

from apps.notifications.views import AdminNotificationViewSet, DeviceTokenRegisterView

router = SimpleRouter()
router.register("admin/notifications", AdminNotificationViewSet, basename="admin-notification")

urlpatterns = [
    path("devices/register/", DeviceTokenRegisterView.as_view(), name="device-register"),
] + router.urls
