from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.locations.views import (
    AddressViewSet,
    AdminServiceAreaViewSet,
    PublicServiceAreaListView,
    autocomplete_location,
    check_service_area,
    reverse_geocode_location,
)

router = SimpleRouter()
router.register("addresses", AddressViewSet, basename="address")
router.register("admin/service-areas", AdminServiceAreaViewSet, basename="admin-service-area")

urlpatterns = [
    path("service-areas/", PublicServiceAreaListView.as_view(), name="service-area-list"),
    path("service-areas/check/", check_service_area, name="service-area-check"),
    path("location/reverse-geocode/", reverse_geocode_location, name="location-reverse-geocode"),
    path("location/autocomplete/", autocomplete_location, name="location-autocomplete"),
    *router.urls,
]
