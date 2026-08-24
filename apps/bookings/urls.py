from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.bookings.views import AdminBookingBalanceCollectionView, AdminBookingOperationView, AdminBookingViewSet, BookingViewSet

router = SimpleRouter()
router.register("bookings", BookingViewSet, basename="booking")
router.register("admin/bookings", AdminBookingViewSet, basename="admin-booking")

urlpatterns = [
    path(
        "admin/bookings/<uuid:booking_id>/start/",
        AdminBookingOperationView.as_view(operation="start"),
        name="admin-booking-start",
    ),
    path(
        "admin/bookings/<uuid:booking_id>/complete/",
        AdminBookingOperationView.as_view(operation="complete"),
        name="admin-booking-complete",
    ),
    path(
        "admin/bookings/<uuid:booking_id>/cancel/",
        AdminBookingOperationView.as_view(operation="cancel"),
        name="admin-booking-cancel",
    ),
    path(
        "admin/bookings/<uuid:booking_id>/record-balance/",
        AdminBookingBalanceCollectionView.as_view(),
        name="admin-booking-record-balance",
    ),
] + router.urls
