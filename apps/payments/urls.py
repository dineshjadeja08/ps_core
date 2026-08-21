from django.urls import path

from apps.payments.views import BookingAdvancePaymentOrderView, PaymentVerifyView, razorpay_webhook

urlpatterns = [
    path(
        "bookings/<uuid:booking_id>/payments/order/",
        BookingAdvancePaymentOrderView.as_view(),
        name="booking-payment-order",
    ),
    path("payments/verify/", PaymentVerifyView.as_view(), name="payment-verify"),
    path("payments/webhooks/razorpay/", razorpay_webhook, name="razorpay-webhook"),
]
