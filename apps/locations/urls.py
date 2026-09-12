from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.locations.views import AddressViewSet, AdminServiceAreaViewSet, check_service_area

router = SimpleRouter()
router.register("addresses", AddressViewSet, basename="address")
router.register("admin/service-areas", AdminServiceAreaViewSet, basename="admin-service-area")

urlpatterns = [
    path("service-areas/check/", check_service_area, name="service-area-check"),
    *router.urls,
]
