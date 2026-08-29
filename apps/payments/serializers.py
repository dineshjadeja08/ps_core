from rest_framework import serializers

from apps.payments.models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    booking_number = serializers.CharField(source="booking.booking_number", read_only=True)
    customer_phone = serializers.CharField(source="booking.customer.phone_number", read_only=True)

    class Meta:
        model = Payment
        fields = (
            "id",
            "booking",
            "booking_number",
            "customer_phone",
            "provider",
            "provider_order_id",
            "provider_payment_id",
            "amount",
            "currency",
            "payment_type",
            "status",
            "signature_verified",
            "idempotency_key",
            "paid_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class PaymentOrderResponseSerializer(serializers.Serializer):
    payment_id = serializers.UUIDField()
    booking_id = serializers.UUIDField()
    provider_order_id = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    amount_paise = serializers.IntegerField()
    currency = serializers.CharField()
    key_id = serializers.CharField(allow_blank=True)


class PaymentVerifyRequestSerializer(serializers.Serializer):
    razorpay_order_id = serializers.CharField()
    razorpay_payment_id = serializers.CharField()
    razorpay_signature = serializers.CharField()


class PaymentVerifyResponseSerializer(serializers.Serializer):
    payment_id = serializers.UUIDField()
    booking_id = serializers.UUIDField()
    payment_status = serializers.CharField()
    booking_status = serializers.CharField()


class WebhookResponseSerializer(serializers.Serializer):
    processed = serializers.BooleanField()
    event = serializers.CharField(allow_blank=True, required=False)
