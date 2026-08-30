from rest_framework.routers import SimpleRouter

from apps.audit.views import AdminAuditLogViewSet

router = SimpleRouter()
router.register("admin/audit-logs", AdminAuditLogViewSet, basename="admin-audit-log")

urlpatterns = router.urls
