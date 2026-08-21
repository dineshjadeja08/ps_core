import hmac
import json
from decimal import Decimal
from hashlib import sha256

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string
from rest_framework import serializers

from apps.bookings.models import Booking, BookingStatus, BookingStatusHistory, PaymentStatus
from apps.notifications.models import NotificationEvent
from apps.notifications.services import emit_notification_event
from apps.payments.models import Payment, PaymentRecordStatus, PaymentType


def create_advance_payment_order(*, booking, user):
    if booking.customer_id != user.id:
        raise serializers.ValidationError("Booking was not found.")
    if booking.booking_status != BookingStatus.PENDING_PAYMENT:
        raise serializers.ValidationError("Booking is not awaiting payment.")

    existing = Payment.objects.filter(
        booking=booking,
        payment_type=PaymentType.BOOKING_ADVANCE,
        status__in=[PaymentRecordStatus.CREATED, PaymentRecordStatus.PENDING, PaymentRecordStatus.SUCCESS],
    ).order_by("-created_at").first()
    if existing and existing.status == PaymentRecordStatus.SUCCESS:
        raise serializers.ValidationError("Payment has already been processed.")
    if existing and existing.provider_order_id:
        return existing, _order_response(existing)

    adapter = import_string(settings.RAZORPAY_ADAPTER)()
    amount_paise = decimal_to_paise(booking.advance_required)
    provider_order = adapter.create_order(
        amount_paise=amount_paise,
        currency="INR",
        receipt=booking.booking_number,
        notes={"booking_id": str(booking.id), "booking_number": booking.booking_number},
    )
    payment = Payment.objects.create(
        booking=booking,
        provider_order_id=provider_order["id"],
        amount=booking.advance_required,
        currency="INR",
        payment_type=PaymentType.BOOKING_ADVANCE,
        status=PaymentRecordStatus.CREATED,
        provider_payload=redact_payload(provider_order),
    )
    return payment, _order_response(payment)


def verify_razorpay_payment(*, order_id, payment_id, signature, user=None, payload=None):
    with transaction.atomic():
        payment = Payment.objects.select_for_update().select_related("booking").get(provider_order_id=order_id)
        booking = Booking.objects.select_for_update().get(id=payment.booking_id)
        if user is not None and booking.customer_id != user.id:
            raise serializers.ValidationError("Payment was not found.")
        if payment.amount != booking.advance_required:
            raise serializers.ValidationError("Payment amount does not match booking advance.")
        if payment.status == PaymentRecordStatus.SUCCESS:
            return payment
        signature_is_valid = verify_payment_signature(order_id=order_id, payment_id=payment_id, signature=signature)
        if not signature_is_valid:
            payment.status = PaymentRecordStatus.FAILED
            payment.provider_payment_id = payment_id
            payment.provider_payload = redact_payload(payload or {})
            payment.save(update_fields=["status", "provider_payment_id", "provider_payload", "updated_at"])
        else:
            payment.provider_payment_id = payment_id
            payment.signature_verified = True
            payment.status = PaymentRecordStatus.SUCCESS
            payment.paid_at = timezone.now()
            payment.provider_payload = redact_payload(payload or {})
            payment.save(
                update_fields=[
                    "provider_payment_id",
                    "signature_verified",
                    "status",
                    "paid_at",
                    "provider_payload",
                    "updated_at",
                ]
            )

            previous_status = booking.booking_status
            booking.advance_paid = payment.amount
            booking.balance_due = booking.total_amount - booking.advance_paid
            booking.payment_status = PaymentStatus.PARTIALLY_PAID
            booking.booking_status = BookingStatus.CONFIRMED
            booking.confirmed_at = timezone.now()
            booking.save(
                update_fields=[
                    "advance_paid",
                    "balance_due",
                    "payment_status",
                    "booking_status",
                    "confirmed_at",
                    "updated_at",
                ]
            )
            if previous_status != BookingStatus.CONFIRMED:
                BookingStatusHistory.objects.create(
                    booking=booking,
                    from_status=previous_status,
                    to_status=BookingStatus.CONFIRMED,
                    changed_by=user,
                    notes="Advance payment verified.",
                )
                emit_notification_event(
                    event=NotificationEvent.BOOKING_CONFIRMED,
                    recipient=booking.customer,
                    booking=booking,
                    payload={"payment_id": str(payment.id)},
                )
            payment.booking = booking
    if not signature_is_valid:
        raise serializers.ValidationError("Payment verification failed.")
    return payment


def process_razorpay_webhook(*, raw_body, signature):
    if not verify_webhook_signature(raw_body=raw_body, signature=signature):
        raise serializers.ValidationError("Invalid webhook signature.")
    try:
        payload = json.loads(raw_body.decode("utf-8") if isinstance(raw_body, bytes) else raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise serializers.ValidationError("Webhook payload is not valid JSON.") from exc
    event = payload.get("event")
    payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    if event != "payment.captured":
        return {"processed": False, "event": event}

    order_id = payment_entity.get("order_id")
    payment_id = payment_entity.get("id")
    if not order_id or not payment_id:
        raise serializers.ValidationError("Webhook payment payload is incomplete.")

    payment = Payment.objects.get(provider_order_id=order_id)
    expected_amount = decimal_to_paise(payment.amount)
    if payment_entity.get("amount") != expected_amount:
        raise serializers.ValidationError("Webhook payment amount does not match.")

    verify_razorpay_payment(
        order_id=order_id,
        payment_id=payment_id,
        signature=make_payment_signature(order_id, payment_id),
        user=None,
        payload=payload,
    )
    return {"processed": True, "event": event}


def verify_payment_signature(*, order_id, payment_id, signature):
    expected = make_payment_signature(order_id, payment_id)
    return hmac.compare_digest(expected, signature or "")


def verify_webhook_signature(*, raw_body, signature):
    body = raw_body if isinstance(raw_body, bytes) else raw_body.encode("utf-8")
    expected = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"), body, sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def make_payment_signature(order_id, payment_id):
    message = f"{order_id}|{payment_id}".encode("utf-8")
    return hmac.new(settings.RAZORPAY_KEY_SECRET.encode("utf-8"), message, sha256).hexdigest()


def decimal_to_paise(amount):
    return int((Decimal(amount) * Decimal("100")).quantize(Decimal("1")))


def redact_payload(payload):
    redacted = dict(payload or {})
    for key in ("secret", "key_secret", "token", "authorization"):
        if key in redacted:
            redacted[key] = "***"
    return redacted


def _order_response(payment):
    return {
        "payment_id": str(payment.id),
        "booking_id": str(payment.booking_id),
        "provider_order_id": payment.provider_order_id,
        "amount": str(payment.amount),
        "amount_paise": decimal_to_paise(payment.amount),
        "currency": payment.currency,
        "key_id": settings.RAZORPAY_KEY_ID,
    }
