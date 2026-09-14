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

    def create_refund(self, *, payment_id, amount_paise, receipt, notes):
        return {
            "id": f"rfnd_{secrets.token_hex(8)}",
            "payment_id": payment_id,
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt,
            "status": "processed",
            "notes": notes,
        }

    def fetch_refund(self, *, refund_id):
        return {"id": refund_id, "status": "processed"}


class RazorpayApiAdapter:
    @staticmethod
    def _client():
        if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
            raise PaymentGatewayConfigurationError("Razorpay keys are not configured.")
        return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

    def create_order(self, *, amount_paise, currency, receipt, notes):
        try:
            return self._client().order.create(
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

    def create_refund(self, *, payment_id, amount_paise, receipt, notes):
        try:
            return self._client().payment.refund(
                payment_id,
                data={
                    "amount": amount_paise,
                    "speed": "normal",
                    "receipt": receipt,
                    "notes": notes,
                },
            )
        except razorpay.errors.BadRequestError as exc:
            raise PaymentGatewayUnavailableError("Razorpay rejected the refund request.") from exc
        except (razorpay.errors.GatewayError, razorpay.errors.ServerError) as exc:
            raise PaymentGatewayUnavailableError("Razorpay refund service is temporarily unavailable.") from exc
        except Exception as exc:
            raise PaymentGatewayUnavailableError("Razorpay refund service is temporarily unavailable.") from exc

    def fetch_refund(self, *, refund_id):
        try:
            return self._client().refund.fetch(refund_id)
        except razorpay.errors.BadRequestError as exc:
            raise PaymentGatewayUnavailableError("Razorpay could not find that refund.") from exc
        except (razorpay.errors.GatewayError, razorpay.errors.ServerError) as exc:
            raise PaymentGatewayUnavailableError("Razorpay refund service is temporarily unavailable.") from exc
        except Exception as exc:
            raise PaymentGatewayUnavailableError("Razorpay refund service is temporarily unavailable.") from exc
