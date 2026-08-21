from rest_framework import serializers


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
