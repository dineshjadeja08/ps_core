from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import serializers
from rest_framework.views import APIView

from apps.audit.models import AuditAction
from apps.audit.services import audit_event
from apps.bookings.models import Booking
from apps.payments.serializers import (
    PaymentOrderResponseSerializer,
    PaymentVerifyRequestSerializer,
    PaymentVerifyResponseSerializer,
    WebhookResponseSerializer,
)
from apps.payments.models import Payment
from apps.payments.services import create_advance_payment_order, process_razorpay_webhook, verify_razorpay_payment


MAX_WEBHOOK_BODY_BYTES = 256 * 1024


class BookingAdvancePaymentOrderView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentOrderResponseSerializer
    throttle_scope = "payment"

    @extend_schema(
        summary="Create Razorpay advance order",
        description="Creates or reuses a Razorpay order for the booking advance. The backend determines the amount.",
        request=None,
        parameters=[OpenApiParameter("booking_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
        responses={status.HTTP_201_CREATED: PaymentOrderResponseSerializer},
    )
    def post(self, request, booking_id):
        try:
            booking = Booking.objects.get(id=booking_id, customer=request.user)
        except Booking.DoesNotExist:
            return Response(
                {"error": {"code": "BOOKING_NOT_FOUND", "message": "Booking was not found.", "details": {}}},
                status=status.HTTP_404_NOT_FOUND,
            )
        payment, response_data = create_advance_payment_order(booking=booking, user=request.user)
        return Response(response_data, status=status.HTTP_201_CREATED)


class PaymentVerifyView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "payment"

    @extend_schema(
        summary="Verify Razorpay payment",
        description="Verifies Razorpay checkout signature and confirms the booking when the advance succeeds.",
        request=PaymentVerifyRequestSerializer,
        responses={status.HTTP_200_OK: PaymentVerifyResponseSerializer},
        examples=[
            OpenApiExample(
                "Verify request",
                value={
                    "razorpay_order_id": "order_123",
                    "razorpay_payment_id": "pay_123",
                    "razorpay_signature": "hmac-signature",
                },
                request_only=True,
            )
        ],
    )
    def post(self, request):
        serializer = PaymentVerifyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payment = verify_razorpay_payment(
                order_id=serializer.validated_data["razorpay_order_id"],
                payment_id=serializer.validated_data["razorpay_payment_id"],
                signature=serializer.validated_data["razorpay_signature"],
                user=request.user,
                payload=request.data,
            )
        except Payment.DoesNotExist:
            return Response(
                {"error": {"code": "PAYMENT_NOT_FOUND", "message": "Payment order was not found.", "details": {}}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {
                "payment_id": payment.id,
                "booking_id": payment.booking_id,
                "payment_status": payment.status,
                "booking_status": payment.booking.booking_status,
            }
        )


@extend_schema(
    summary="Razorpay webhook",
    description="Processes Razorpay webhooks idempotently after validating the webhook signature.",
    request=OpenApiTypes.OBJECT,
    responses={status.HTTP_200_OK: WebhookResponseSerializer},
)
@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def razorpay_webhook(request):
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not signature:
        audit_event(
            action=AuditAction.PAYMENT_WEBHOOK_REJECTED,
            resource_type="payment_webhook",
            request=request,
            metadata={"reason": "missing_signature"},
        )
        raise serializers.ValidationError("Webhook signature is required.")
    if len(request.body) > MAX_WEBHOOK_BODY_BYTES:
        audit_event(
            action=AuditAction.PAYMENT_WEBHOOK_REJECTED,
            resource_type="payment_webhook",
            request=request,
            metadata={"reason": "payload_too_large", "size_bytes": len(request.body)},
        )
        raise serializers.ValidationError("Webhook payload is too large.")
    audit_event(
        action=AuditAction.PAYMENT_WEBHOOK_RECEIVED,
        resource_type="payment_webhook",
        request=request,
        metadata={"has_signature": bool(signature)},
    )
    try:
        result = process_razorpay_webhook(raw_body=request.body, signature=signature)
    except Exception:
        audit_event(
            action=AuditAction.PAYMENT_WEBHOOK_REJECTED,
            resource_type="payment_webhook",
            request=request,
            metadata={"has_signature": bool(signature)},
        )
        raise
    return Response(result)


razorpay_webhook.cls.throttle_scope = "webhook"
