from rest_framework.routers import SimpleRouter

from django.urls import path

from apps.operations.views import (
    AdminDashboardSummaryView,
    AdminFAQViewSet,
    AdminGlobalSearchView,
    AdminHomepageBannerViewSet,
    AdminLeadViewSet,
    AdminReportsSummaryView,
    AdminSettingsView,
    PublicFAQListView,
    PublicHomepageBannerListView,
)

router = SimpleRouter()
router.register("admin/leads", AdminLeadViewSet, basename="admin-lead")
router.register("admin/faqs", AdminFAQViewSet, basename="admin-faq")
router.register("admin/homepage-banners", AdminHomepageBannerViewSet, basename="admin-homepage-banner")

urlpatterns = [
    path("faqs/", PublicFAQListView.as_view(), name="public-faq-list"),
    path("homepage-banners/", PublicHomepageBannerListView.as_view(), name="public-homepage-banner-list"),
    path("admin/dashboard/summary/", AdminDashboardSummaryView.as_view(), name="admin-dashboard-summary"),
    path("admin/search/", AdminGlobalSearchView.as_view(), name="admin-global-search"),
    path("admin/reports/summary/", AdminReportsSummaryView.as_view(), name="admin-reports-summary"),
    path("admin/settings/", AdminSettingsView.as_view(), name="admin-settings"),
] + router.urls
