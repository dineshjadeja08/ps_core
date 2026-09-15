import hashlib
import hmac
import json
from decimal import Decimal
from hashlib import sha256

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.module_loading import import_string
from rest_framework import serializers

from apps.bookings.models import Booking, BookingStatus, BookingStatusHistory, PaymentStatus
from apps.notifications.models import NotificationEvent
from apps.notifications.services import emit_notification_event
from apps.payments.models import (
    Payment,
    PaymentRecordStatus,
    PaymentType,
    PaymentWebhookEvent,
    WebhookProcessingStatus,
)
from common.monitoring import report_operational_failure


ACTIVE_ADVANCE_STATUSES = (
    PaymentRecordStatus.CREATED,
    PaymentRecordStatus.PENDING,
    PaymentRecordStatus.SUCCESS,
)


@transaction.atomic
def create_advance_payment_order(*, booking, user, idempotency_key):
    booking = Booking.objects.select_for_update().select_related("customer").get(pk=booking.pk)
    if booking.customer_id != user.id:
        raise serializers.ValidationError("Booking was not found.")
    if booking.booking_status not in {BookingStatus.PENDING_PAYMENT, BookingStatus.PAYMENT_FAILED}:
        raise serializers.ValidationError("Booking is not awaiting payment.")

    keyed = Payment.objects.filter(
        booking=booking,
        payment_type=PaymentType.BOOKING_ADVANCE,
        idempotency_key=idempotency_key,
    ).first()
    if keyed:
        if keyed.status == PaymentRecordStatus.FAILED:
            raise serializers.ValidationError(
                {"idempotency_key": "The previous payment attempt failed. Start a new attempt with a new Idempotency-Key."}
            )
        return keyed, _order_response(keyed)

    existing = Payment.objects.filter(
        booking=booking,
        payment_type=PaymentType.BOOKING_ADVANCE,
        status__in=ACTIVE_ADVANCE_STATUSES,
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
        idempotency_key=idempotency_key,
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
            payment.booking = booking
            return payment

        signature_is_valid = verify_payment_signature(order_id=order_id, payment_id=payment_id, signature=signature)
        if not signature_is_valid:
            _mark_payment_failed(payment=payment, booking=booking, provider_payment_id=payment_id, payload=payload)
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
            _confirm_booking_after_payment(booking=booking, payment=payment, changed_by=user)
            payment.booking = booking

    if not signature_is_valid:
        raise serializers.ValidationError("Payment verification failed.")
    return payment


@transaction.atomic
def create_refund(*, payment_id, amount, idempotency_key, requested_by, reason=""):
    source = (
        Payment.objects.select_for_update()
        .select_related("booking", "booking__customer")
        .get(id=payment_id)
    )
    booking = Booking.objects.select_for_update().get(id=source.booking_id)
    if source.payment_type == PaymentType.REFUND or source.status not in {
        PaymentRecordStatus.SUCCESS,
        PaymentRecordStatus.REFUNDED,
    }:
        raise serializers.ValidationError("Only a successful payment can be refunded.")
    if not source.provider_payment_id:
        raise serializers.ValidationError("This payment does not have a Razorpay payment reference.")

    existing = Payment.objects.filter(
        booking=booking,
        payment_type=PaymentType.REFUND,
        idempotency_key=idempotency_key,
    ).first()
    if existing:
        return existing

    already_requested = source.refunds.exclude(status=PaymentRecordStatus.FAILED).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    remaining = source.amount - already_requested
    amount = Decimal(amount)
    if amount <= 0 or amount > remaining:
        raise serializers.ValidationError({"amount": f"Refund amount must be between 0.01 and {remaining}."})

    receipt_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:12]
    receipt = f"refund-{str(source.id)[:8]}-{receipt_hash}"
    provider_refund = import_string(settings.RAZORPAY_ADAPTER)().create_refund(
        payment_id=source.provider_payment_id,
        amount_paise=decimal_to_paise(amount),
        receipt=receipt,
        notes={
            "booking_id": str(booking.id),
            "booking_number": booking.booking_number,
            "reason": reason[:200],
            "requested_by": str(requested_by.id),
        },
    )
    status = _refund_status(provider_refund.get("status"))
    refund = Payment.objects.create(
        booking=booking,
        parent_payment=source,
        provider_refund_id=provider_refund["id"],
        amount=amount,
        currency=source.currency,
        payment_type=PaymentType.REFUND,
        status=status,
        provider_payload=redact_payload(provider_refund),
        idempotency_key=idempotency_key,
        refunded_at=timezone.now() if status == PaymentRecordStatus.SUCCESS else None,
    )
    _apply_refund_state(booking=booking, source=source)
    emit_notification_event(
        event=NotificationEvent.REFUND_INITIATED,
        recipient=booking.customer,
        booking=booking,
        payload={"refund_id": str(refund.id), "amount": str(refund.amount)},
    )
    if status == PaymentRecordStatus.SUCCESS:
        emit_notification_event(
            event=NotificationEvent.REFUND_COMPLETED,
            recipient=booking.customer,
            booking=booking,
            payload={"refund_id": str(refund.id), "amount": str(refund.amount)},
        )
    return refund


@transaction.atomic
def reconcile_refund(*, refund_id):
    refund = Payment.objects.select_for_update().select_related("parent_payment", "booking").get(
        id=refund_id,
        payment_type=PaymentType.REFUND,
    )
    booking = Booking.objects.select_for_update().get(id=refund.booking_id)
    if not refund.provider_refund_id or not refund.parent_payment:
        raise serializers.ValidationError("Refund provider references are incomplete.")
    provider_refund = import_string(settings.RAZORPAY_ADAPTER)().fetch_refund(refund_id=refund.provider_refund_id)
    previous_status = refund.status
    refund.status = _refund_status(provider_refund.get("status"))
    refund.provider_payload = redact_payload(provider_refund)
    refund.refunded_at = timezone.now() if refund.status == PaymentRecordStatus.SUCCESS else None
    refund.save(update_fields=["status", "provider_payload", "refunded_at", "updated_at"])
    _apply_refund_state(booking=booking, source=refund.parent_payment)
    if previous_status != PaymentRecordStatus.SUCCESS and refund.status == PaymentRecordStatus.SUCCESS:
        emit_notification_event(
            event=NotificationEvent.REFUND_COMPLETED,
            recipient=booking.customer,
            booking=booking,
            payload={"refund_id": str(refund.id), "amount": str(refund.amount)},
        )
    return refund


def process_razorpay_webhook(*, raw_body, signature):
    if not verify_webhook_signature(raw_body=raw_body, signature=signature):
        raise serializers.ValidationError("Invalid webhook signature.")
    try:
        payload = json.loads(raw_body.decode("utf-8") if isinstance(raw_body, bytes) else raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise serializers.ValidationError("Webhook payload is not valid JSON.") from exc

    body = raw_body if isinstance(raw_body, bytes) else raw_body.encode("utf-8")
    payload_hash = hashlib.sha256(body).hexdigest()
    event_name = str(payload.get("event", ""))
    with transaction.atomic():
        record, _ = PaymentWebhookEvent.objects.get_or_create(
            payload_hash=payload_hash,
            defaults={"event": event_name},
        )
        record = PaymentWebhookEvent.objects.select_for_update().get(pk=record.pk)
        if record.status == WebhookProcessingStatus.PROCESSED:
            return {"processed": True, "duplicate": True, "event": event_name}
        processing_is_fresh = (
            record.status == WebhookProcessingStatus.PROCESSING
            and record.attempts > 0
            and record.updated_at >= timezone.now() - timezone.timedelta(minutes=5)
        )
        if processing_is_fresh:
            return {"processed": False, "duplicate": True, "event": event_name}
        record.attempts += 1
        record.status = WebhookProcessingStatus.PROCESSING
        record.last_error = ""
        record.save(update_fields=["attempts", "status", "last_error", "updated_at"])
    try:
        processed = _dispatch_webhook(event_name=event_name, payload=payload)
    except Exception as exc:
        PaymentWebhookEvent.objects.filter(pk=record.pk).update(
            status=WebhookProcessingStatus.FAILED,
            last_error=type(exc).__name__,
        )
        report_operational_failure(
            "payment",
            "Razorpay webhook processing failed",
            exception=exc,
            context={"event": event_name, "webhook_record_id": record.id},
        )
        raise

    PaymentWebhookEvent.objects.filter(pk=record.pk).update(
        status=WebhookProcessingStatus.PROCESSED,
        processed_at=timezone.now(),
        last_error="",
    )
    return {"processed": processed, "duplicate": False, "event": event_name}


def _dispatch_webhook(*, event_name, payload):
    if event_name == "payment.captured":
        entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        order_id = entity.get("order_id")
        payment_id = entity.get("id")
        if not order_id or not payment_id:
            raise serializers.ValidationError("Webhook payment payload is incomplete.")
        payment = Payment.objects.get(provider_order_id=order_id)
        if entity.get("amount") != decimal_to_paise(payment.amount):
            raise serializers.ValidationError("Webhook payment amount does not match.")
        verify_razorpay_payment(
            order_id=order_id,
            payment_id=payment_id,
            signature=make_payment_signature(order_id, payment_id),
            user=None,
            payload=payload,
        )
        return True
    if event_name == "payment.failed":
        _process_payment_failed_webhook(payload)
        return True
    if event_name in {"refund.created", "refund.processed", "refund.failed"}:
        _process_refund_webhook(payload)
        return True
    return False


@transaction.atomic
def _process_payment_failed_webhook(payload):
    entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    order_id = entity.get("order_id")
    if not order_id:
        raise serializers.ValidationError("Webhook payment payload is incomplete.")
    payment = Payment.objects.select_for_update().get(provider_order_id=order_id)
    booking = Booking.objects.select_for_update().get(id=payment.booking_id)
    if payment.status != PaymentRecordStatus.SUCCESS:
        _mark_payment_failed(
            payment=payment,
            booking=booking,
            provider_payment_id=entity.get("id"),
            payload=payload,
        )


@transaction.atomic
def _process_refund_webhook(payload):
    entity = payload.get("payload", {}).get("refund", {}).get("entity", {})
    refund_id = entity.get("id")
    source_payment_id = entity.get("payment_id")
    if not refund_id or not source_payment_id:
        raise serializers.ValidationError("Webhook refund payload is incomplete.")
    source = Payment.objects.select_for_update().select_related("booking").get(provider_payment_id=source_payment_id)
    booking = Booking.objects.select_for_update().get(id=source.booking_id)
    status = _refund_status(entity.get("status"))
    amount = Decimal(entity.get("amount", 0)) / Decimal("100")
    refund, created = Payment.objects.select_for_update().get_or_create(
        provider_refund_id=refund_id,
        defaults={
            "booking": booking,
            "parent_payment": source,
            "amount": amount,
            "currency": entity.get("currency") or source.currency,
            "payment_type": PaymentType.REFUND,
            "status": status,
            "idempotency_key": f"webhook-{refund_id}",
            "provider_payload": redact_payload(entity),
            "refunded_at": timezone.now() if status == PaymentRecordStatus.SUCCESS else None,
        },
    )
    previous_status = refund.status
    if not created:
        refund.status = status
        refund.provider_payload = redact_payload(entity)
        refund.refunded_at = timezone.now() if status == PaymentRecordStatus.SUCCESS else None
        refund.save(update_fields=["status", "provider_payload", "refunded_at", "updated_at"])
    _apply_refund_state(booking=booking, source=source)
    if created:
        emit_notification_event(
            event=NotificationEvent.REFUND_INITIATED,
            recipient=booking.customer,
            booking=booking,
            payload={"refund_id": str(refund.id), "amount": str(refund.amount)},
        )
    if status == PaymentRecordStatus.SUCCESS and (created or previous_status != PaymentRecordStatus.SUCCESS):
        emit_notification_event(
            event=NotificationEvent.REFUND_COMPLETED,
            recipient=booking.customer,
            booking=booking,
            payload={"refund_id": str(refund.id), "amount": str(refund.amount)},
        )


def _mark_payment_failed(*, payment, booking, provider_payment_id=None, payload=None):
    transitioned_to_failed = payment.status != PaymentRecordStatus.FAILED
    payment.status = PaymentRecordStatus.FAILED
    if provider_payment_id:
        payment.provider_payment_id = provider_payment_id
    payment.provider_payload = redact_payload(payload or {})
    payment.save(update_fields=["status", "provider_payment_id", "provider_payload", "updated_at"])
    if booking.booking_status in {BookingStatus.PENDING_PAYMENT, BookingStatus.PAYMENT_FAILED}:
        booking.booking_status = BookingStatus.PAYMENT_FAILED
        booking.payment_status = PaymentStatus.FAILED
        booking.save(update_fields=["booking_status", "payment_status", "updated_at"])
    if transitioned_to_failed:
        report_operational_failure(
            "payment",
            "Advance payment failed",
            context={"payment_id": payment.id, "booking_id": booking.id},
            level="warning",
        )
        emit_notification_event(
            event=NotificationEvent.PAYMENT_FAILED,
            recipient=booking.customer,
            booking=booking,
            payload={"payment_id": str(payment.id)},
        )


def _confirm_booking_after_payment(*, booking, payment, changed_by):
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
            changed_by=changed_by,
            notes="Advance payment verified.",
        )
        emit_notification_event(
            event=NotificationEvent.PAYMENT_SUCCESSFUL,
            recipient=booking.customer,
            booking=booking,
            payload={"payment_id": str(payment.id), "amount": str(payment.amount)},
        )
        emit_notification_event(
            event=NotificationEvent.BOOKING_CONFIRMED,
            recipient=booking.customer,
            booking=booking,
            payload={"payment_id": str(payment.id)},
        )
    try:
        from apps.operations.services import mark_booking_payment_paid

        mark_booking_payment_paid(booking=booking, payment=payment, performed_by=changed_by)
    except Exception as exc:
        report_operational_failure(
            "booking",
            "Paid booking could not be synchronized to the operations lead",
            exception=exc,
            context={"booking_id": booking.id, "payment_id": payment.id},
        )


def _apply_refund_state(*, booking, source):
    successful = source.refunds.filter(status=PaymentRecordStatus.SUCCESS).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    pending = source.refunds.filter(status__in=[PaymentRecordStatus.CREATED, PaymentRecordStatus.PENDING]).exists()
    if successful >= source.amount:
        source.status = PaymentRecordStatus.REFUNDED
        source.save(update_fields=["status", "updated_at"])
        booking.payment_status = PaymentStatus.REFUNDED
        booking.booking_status = BookingStatus.REFUNDED
        booking.save(update_fields=["payment_status", "booking_status", "updated_at"])
    elif pending:
        booking.booking_status = BookingStatus.REFUND_PENDING
        booking.save(update_fields=["booking_status", "updated_at"])
    elif booking.booking_status == BookingStatus.REFUND_PENDING:
        booking.booking_status = BookingStatus.CANCELLED if booking.cancelled_at else BookingStatus.CONFIRMED
        booking.save(update_fields=["booking_status", "updated_at"])


def _refund_status(value):
    return {
        "processed": PaymentRecordStatus.SUCCESS,
        "failed": PaymentRecordStatus.FAILED,
        "pending": PaymentRecordStatus.PENDING,
        "created": PaymentRecordStatus.PENDING,
    }.get(str(value or "").lower(), PaymentRecordStatus.PENDING)


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
    sensitive_keys = {"secret", "key_secret", "token", "authorization", "contact", "email"}
    if isinstance(payload, dict):
        return {
            key: "***" if str(key).lower() in sensitive_keys else redact_payload(value)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [redact_payload(value) for value in payload]
    return payload


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
