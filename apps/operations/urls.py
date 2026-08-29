from rest_framework.routers import SimpleRouter

from apps.operations.views import AdminFAQViewSet, AdminHomepageBannerViewSet, AdminLeadViewSet

router = SimpleRouter()
router.register("admin/leads", AdminLeadViewSet, basename="admin-lead")
router.register("admin/faqs", AdminFAQViewSet, basename="admin-faq")
router.register("admin/homepage-banners", AdminHomepageBannerViewSet, basename="admin-homepage-banner")

urlpatterns = router.urls
