from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.payments.views import AdminBookingInvoiceDownloadView, AdminPaymentViewSet, BookingAdvancePaymentOrderView, BookingInvoiceDownloadView, PaymentVerifyView, razorpay_webhook

router = SimpleRouter()
router.register("admin/payments", AdminPaymentViewSet, basename="admin-payment")

urlpatterns = [
    path("bookings/<uuid:booking_id>/invoice/", BookingInvoiceDownloadView.as_view(), name="booking-invoice"),
    path("admin/bookings/<uuid:booking_id>/invoice/", AdminBookingInvoiceDownloadView.as_view(), name="admin-booking-invoice"),
    path(
        "bookings/<uuid:booking_id>/payments/order/",
        BookingAdvancePaymentOrderView.as_view(),
        name="booking-payment-order",
    ),
    path("payments/verify/", PaymentVerifyView.as_view(), name="payment-verify"),
    path("payments/webhooks/razorpay/", razorpay_webhook, name="razorpay-webhook"),
] + router.urls
