from rest_framework.routers import SimpleRouter

from apps.accounts.views import AdminCustomerViewSet, AdminStaffGroupViewSet, AdminStaffViewSet

router = SimpleRouter()
router.register("admin/customers", AdminCustomerViewSet, basename="admin-customer")
router.register("admin/staff", AdminStaffViewSet, basename="admin-staff")
router.register("admin/staff-groups", AdminStaffGroupViewSet, basename="admin-staff-group")

urlpatterns = router.urls
