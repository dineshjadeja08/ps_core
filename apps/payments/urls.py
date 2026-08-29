from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.payments.views import AdminPaymentViewSet, BookingAdvancePaymentOrderView, PaymentVerifyView, razorpay_webhook

router = SimpleRouter()
router.register("admin/payments", AdminPaymentViewSet, basename="admin-payment")

urlpatterns = [
    path(
        "bookings/<uuid:booking_id>/payments/order/",
        BookingAdvancePaymentOrderView.as_view(),
        name="booking-payment-order",
    ),
    path("payments/verify/", PaymentVerifyView.as_view(), name="payment-verify"),
    path("payments/webhooks/razorpay/", razorpay_webhook, name="razorpay-webhook"),
] + router.urls
