from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.locations.views import AddressViewSet, check_service_area

router = SimpleRouter()
router.register("addresses", AddressViewSet, basename="address")

urlpatterns = [
    path("service-areas/check/", check_service_area, name="service-area-check"),
    *router.urls,
]
