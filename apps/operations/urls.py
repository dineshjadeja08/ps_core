from rest_framework.routers import SimpleRouter

from django.urls import path

from apps.operations.views import AdminFAQViewSet, AdminHomepageBannerViewSet, AdminLeadViewSet, AdminReportsSummaryView, AdminSettingsView

router = SimpleRouter()
router.register("admin/leads", AdminLeadViewSet, basename="admin-lead")
router.register("admin/faqs", AdminFAQViewSet, basename="admin-faq")
router.register("admin/homepage-banners", AdminHomepageBannerViewSet, basename="admin-homepage-banner")

urlpatterns = [
    path("admin/reports/summary/", AdminReportsSummaryView.as_view(), name="admin-reports-summary"),
    path("admin/settings/", AdminSettingsView.as_view(), name="admin-settings"),
] + router.urls
