from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.reviews.views import AdminReviewViewSet, BookingReviewCreateView, ServiceReviewListView

router = SimpleRouter()
router.register("admin/reviews", AdminReviewViewSet, basename="admin-review")

urlpatterns = [
    path("bookings/<uuid:booking_id>/review/", BookingReviewCreateView.as_view(), name="booking-review-create"),
    path("services/<uuid:service_id>/reviews/", ServiceReviewListView.as_view(), name="service-review-list"),
] + router.urls
