from rest_framework.routers import SimpleRouter

from apps.accounts.views import AdminCustomerViewSet

router = SimpleRouter()
router.register("admin/customers", AdminCustomerViewSet, basename="admin-customer")

urlpatterns = router.urls
