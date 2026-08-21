from unittest.mock import patch

import pytest
from django.test import override_settings
from rest_framework import serializers

from apps.payments.providers import RazorpayApiAdapter


def test_razorpay_api_adapter_creates_order_with_sdk():
    captured = {}

    class FakeOrderClient:
        def create(self, *, data):
            captured["data"] = data
            return {"id": "order_test_123", "amount": data["amount"], "currency": data["currency"]}

    class FakeClient:
        def __init__(self, *, auth):
            captured["auth"] = auth
            self.order = FakeOrderClient()

    with override_settings(RAZORPAY_KEY_ID="rzp_test_id", RAZORPAY_KEY_SECRET="secret"):
        with patch("apps.payments.providers.razorpay.Client", FakeClient):
            response = RazorpayApiAdapter().create_order(
                amount_paise=19900,
                currency="INR",
                receipt="PS-123",
                notes={"booking_id": "booking-1"},
            )

    assert response["id"] == "order_test_123"
    assert captured["auth"] == ("rzp_test_id", "secret")
    assert captured["data"] == {
        "amount": 19900,
        "currency": "INR",
        "receipt": "PS-123",
        "notes": {"booking_id": "booking-1"},
    }


def test_razorpay_api_adapter_requires_keys():
    with override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=""):
        with pytest.raises(serializers.ValidationError):
            RazorpayApiAdapter().create_order(amount_paise=19900, currency="INR", receipt="PS-123", notes={})
