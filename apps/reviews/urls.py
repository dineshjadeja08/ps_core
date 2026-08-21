from django.urls import path

from apps.reviews.views import BookingReviewCreateView, ServiceReviewListView

urlpatterns = [
    path("bookings/<uuid:booking_id>/review/", BookingReviewCreateView.as_view(), name="booking-review-create"),
    path("services/<uuid:service_id>/reviews/", ServiceReviewListView.as_view(), name="service-review-list"),
]
