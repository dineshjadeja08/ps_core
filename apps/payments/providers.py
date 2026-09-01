import secrets
from django.conf import settings
from rest_framework.exceptions import APIException
import razorpay


class PaymentGatewayConfigurationError(APIException):
    status_code = 500
    default_code = "payment_gateway_not_configured"
    default_detail = "Payment gateway is not configured."


class PaymentGatewayUnavailableError(APIException):
    status_code = 502
    default_code = "payment_gateway_unavailable"
    default_detail = "Payment gateway is temporarily unavailable."


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
            raise PaymentGatewayConfigurationError("Razorpay keys are not configured.")

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
        except razorpay.errors.BadRequestError as exc:
            raise PaymentGatewayUnavailableError("Razorpay rejected the order request.") from exc
        except (razorpay.errors.GatewayError, razorpay.errors.ServerError) as exc:
            raise PaymentGatewayUnavailableError("Razorpay order service is temporarily unavailable.") from exc
        except Exception as exc:
            raise PaymentGatewayUnavailableError("Razorpay order service is temporarily unavailable.") from exc
