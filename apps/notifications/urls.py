from rest_framework.routers import SimpleRouter

from apps.notifications.views import AdminNotificationViewSet

router = SimpleRouter()
router.register("admin/notifications", AdminNotificationViewSet, basename="admin-notification")

urlpatterns = router.urls
