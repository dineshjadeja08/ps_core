import secrets
from django.conf import settings
from rest_framework import serializers
import razorpay


class LocalRazorpayAdapter:
    def create_order(self, *, amount_paise, currency, receipt, notes):
        return {
            "id": f"order_{secrets.token_hex(8)}",
            "amount": amount_paise,
            "currency": currency,
            "receipt": receipt,
            "status": "created",
            "notes": notes,
        }


class RazorpayApiAdapter:
    def create_order(self, *, amount_paise, currency, receipt, notes):
        if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
            raise serializers.ValidationError("Razorpay test keys are not configured.")

        try:
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            return client.order.create(
                data={
                    "amount": amount_paise,
                    "currency": currency,
                    "receipt": receipt,
                    "notes": notes,
                }
            )
        except Exception as exc:
            raise serializers.ValidationError("Razorpay order service is unavailable.") from exc
