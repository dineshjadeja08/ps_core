from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.audit.models import AuditAction
from apps.audit.services import audit_event
from apps.bookings.models import Booking, PaymentStatus as BookingPaymentStatus
from apps.notifications.models import Notification, NotificationChannel, NotificationEvent
from apps.notifications.services import send_notification
from apps.operations.models import (
    Lead,
    LeadActivity,
    LeadActivityAction,
    LeadFunnelStatus,
    LeadPaymentStatus,
    LeadSource,
    LeadStatus,
    ManualPaymentMethod,
)
from apps.payments.models import Payment, PaymentProvider, PaymentRecordStatus, PaymentType

OPEN_FUNNEL_STATUSES = {
    LeadFunnelStatus.VISITED,
    LeadFunnelStatus.CART_ADDED,
    LeadFunnelStatus.UNPAID,
}
FUNNEL_RANK = {
    LeadFunnelStatus.VISITED: 10,
    LeadFunnelStatus.CART_ADDED: 20,
    LeadFunnelStatus.UNPAID: 30,
    LeadFunnelStatus.BOOKED: 40,
    LeadFunnelStatus.PAID: 50,
    LeadFunnelStatus.CANCELLED: 60,
    LeadFunnelStatus.LOST: 70,
}
PAYMENT_RANK = {
    LeadPaymentStatus.NOT_REQUIRED: 10,
    LeadPaymentStatus.PENDING: 20,
    LeadPaymentStatus.LINK_SENT: 30,
    LeadPaymentStatus.FAILED: 35,
    LeadPaymentStatus.PAID: 40,
    LeadPaymentStatus.REFUNDED: 50,
}


def capture_authenticated_service_view(*, user, service, request=None):
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_verified", False):
        return None
    if not getattr(user, "phone_number", ""):
        return None
    return upsert_lead(
        customer=user,
        mobile_number=user.phone_number,
        customer_name=_customer_name(user),
        service=service,
        source=LeadSource.SERVICE_VIEW,
        funnel_status=LeadFunnelStatus.VISITED,
        payment_status=LeadPaymentStatus.NOT_REQUIRED,
        action=LeadActivityAction.SERVICE_VIEWED,
        request=request,
        note="Authenticated customer viewed service details.",
    )


def mark_checkout_started(*, customer, service, request=None, note="Checkout started."):
    return upsert_lead(
        customer=customer,
        mobile_number=customer.phone_number,
        customer_name=_customer_name(customer),
        service=service,
        source=LeadSource.CHECKOUT,
        funnel_status=LeadFunnelStatus.UNPAID,
        payment_status=LeadPaymentStatus.PENDING,
        action=LeadActivityAction.CHECKOUT_STARTED,
        request=request,
        note=note,
    )


def link_booking_to_lead(*, booking, request=None):
    lead = upsert_lead(
        customer=booking.customer,
        mobile_number=booking.customer.phone_number,
        customer_name=_customer_name(booking.customer),
        service=booking.service,
        source=LeadSource.CHECKOUT,
        funnel_status=LeadFunnelStatus.BOOKED,
        payment_status=LeadPaymentStatus.PENDING if booking.advance_required > Decimal("0.00") else LeadPaymentStatus.NOT_REQUIRED,
        action=LeadActivityAction.BOOKING_CREATED,
        request=request,
        note=f"Booking {booking.booking_number} created.",
    )
    lead.converted_booking = booking
    lead.quoted_amount = booking.total_amount
    lead.advance_amount = booking.advance_required
    lead.balance_amount = booking.balance_due
    lead.address = _address_text(booking.address_snapshot)
    lead.city = booking.address_snapshot.get("city", "") or lead.city
    lead.pincode = booking.address_snapshot.get("postal_code", "") or lead.pincode
    lead.preferred_date = booking.service_date
    lead.preferred_slot = f"{booking.time_slot.start_time:%H:%M}-{booking.time_slot.end_time:%H:%M}"
    lead.save(
        update_fields=[
            "converted_booking",
            "quoted_amount",
            "advance_amount",
            "balance_amount",
            "address",
            "city",
            "pincode",
            "preferred_date",
            "preferred_slot",
            "updated_at",
        ]
    )
    return lead


def mark_booking_payment_paid(*, booking, payment=None, performed_by=None):
    lead = Lead.objects.filter(converted_booking=booking).order_by("-updated_at").first()
    if not lead:
        lead = link_booking_to_lead(booking=booking)
    previous = {"payment_status": lead.payment_status, "funnel_status": lead.funnel_status}
    lead.payment_status = LeadPaymentStatus.PAID
    lead.funnel_status = LeadFunnelStatus.PAID
    lead.last_activity_at = timezone.now()
    lead.save(update_fields=["payment_status", "funnel_status", "last_activity_at", "updated_at"])
    record_lead_activity(
        lead=lead,
        action=LeadActivityAction.PAYMENT_CONFIRMED,
        previous_value=previous,
        new_value={"payment_status": lead.payment_status, "funnel_status": lead.funnel_status, "payment_id": str(payment.id) if payment else ""},
        performed_by=performed_by,
        note="Payment verified.",
    )
    return lead


@transaction.atomic
def upsert_lead(
    *,
    mobile_number,
    customer_name,
    service=None,
    customer=None,
    source,
    funnel_status,
    payment_status,
    action,
    request=None,
    note="",
):
    lead = (
        Lead.objects.select_for_update()
        .filter(
            primary_mobile=mobile_number,
            required_service=service,
            funnel_status__in=OPEN_FUNNEL_STATUSES,
        )
        .order_by("-last_activity_at")
        .first()
    )
    created = lead is None
    if created:
        lead = Lead(
            customer=customer,
            customer_name=customer_name or mobile_number,
            primary_mobile=mobile_number,
            required_service=service,
            source=source,
            status=LeadStatus.NEW,
            funnel_status=funnel_status,
            payment_status=payment_status,
            first_seen_at=timezone.now(),
        )
    previous = {
        "source": lead.source,
        "funnel_status": lead.funnel_status,
        "payment_status": lead.payment_status,
    }
    lead.customer = lead.customer or customer
    lead.customer_name = lead.customer_name or customer_name or mobile_number
    lead.source = source if created else lead.source
    lead.funnel_status = _max_funnel_status(lead.funnel_status, funnel_status)
    lead.payment_status = _max_payment_status(lead.payment_status, payment_status)
    lead.last_activity_at = timezone.now()
    lead.save()
    record_lead_activity(
        lead=lead,
        action=action,
        previous_value={} if created else previous,
        new_value={"source": lead.source, "funnel_status": lead.funnel_status, "payment_status": lead.payment_status},
        performed_by=customer if getattr(customer, "is_authenticated", False) else None,
        request=request,
        note=note,
    )
    return lead


@transaction.atomic
def send_lead_payment_link(*, lead, performed_by, request=None, channel=NotificationChannel.SMS):
    if lead.payment_status == LeadPaymentStatus.PAID:
        raise serializers.ValidationError("Lead is already paid.")
    if not lead.advance_amount or lead.advance_amount <= Decimal("0.00"):
        raise serializers.ValidationError("Lead does not have an advance amount.")
    if lead.payment_link_expires_at and lead.payment_link_expires_at > timezone.now() and lead.payment_link_url:
        return lead, False

    expires_at = timezone.now() + timezone.timedelta(hours=getattr(settings, "LEAD_PAYMENT_LINK_EXPIRY_HOURS", 24))
    lead.payment_link_provider_id = f"lead-link-{lead.id}"
    lead.payment_link_url = _lead_payment_url(lead)
    previous = {"payment_status": lead.payment_status, "payment_link_url": bool(lead.payment_link_url)}
    lead.payment_link_expires_at = expires_at
    lead.payment_status = LeadPaymentStatus.LINK_SENT
    lead.last_activity_at = timezone.now()
    lead.save(
        update_fields=[
            "payment_link_provider_id",
            "payment_link_url",
            "payment_link_expires_at",
            "payment_status",
            "last_activity_at",
            "updated_at",
        ]
    )
    record_lead_activity(
        lead=lead,
        action=LeadActivityAction.PAYMENT_LINK_CREATED,
        previous_value=previous,
        new_value={"payment_status": lead.payment_status, "expires_at": expires_at.isoformat()},
        performed_by=performed_by,
        request=request,
        note="Payment link created for unpaid lead.",
    )
    notification = Notification.objects.create(
        recipient=lead.customer,
        booking=lead.converted_booking,
        event=NotificationEvent.PAYMENT_PENDING,
        channel=channel,
        title="Payment link",
        message=f"Purple Squad advance payment link: {lead.payment_link_url}",
        payload={"lead_id": str(lead.id), "payment_link_url": lead.payment_link_url},
    )
    send_notification(notification)
    record_lead_activity(
        lead=lead,
        action=LeadActivityAction.PAYMENT_LINK_SENT,
        new_value={"notification_id": str(notification.id), "channel": channel, "status": notification.status},
        performed_by=performed_by,
        request=request,
        note="Payment link delivery attempted.",
    )
    audit_event(
        action=AuditAction.ADMIN_PAYMENT_LINK_CREATED,
        actor=performed_by,
        request=request,
        resource_type="lead",
        resource_id=lead.id,
        metadata={"lead_id": str(lead.id), "channel": channel},
    )
    return lead, True


@transaction.atomic
def record_lead_contact(*, lead, performed_by, note, request=None):
    lead.last_contacted_at = timezone.now()
    lead.last_activity_at = timezone.now()
    if note:
        lead.admin_notes = "\n".join(part for part in [lead.admin_notes, note] if part)
    lead.save(update_fields=["last_contacted_at", "last_activity_at", "admin_notes", "updated_at"])
    record_lead_activity(
        lead=lead,
        action=LeadActivityAction.CALL_COMPLETED,
        note=note,
        performed_by=performed_by,
        request=request,
    )
    return lead


@transaction.atomic
def record_manual_lead_payment(*, lead, performed_by, amount, method, reference, payment_date, note="", request=None):
    if method not in ManualPaymentMethod.values:
        raise serializers.ValidationError("Unsupported manual payment method.")
    if not reference and not note:
        raise serializers.ValidationError("Add a transaction reference or note.")
    if amount <= Decimal("0.00"):
        raise serializers.ValidationError("Amount must be greater than zero.")
    if not lead.converted_booking_id:
        raise serializers.ValidationError("Manual payment requires a linked booking.")

    booking = Booking.objects.select_for_update().get(id=lead.converted_booking_id)
    payment = Payment.objects.create(
        booking=booking,
        provider=PaymentProvider.OFFLINE,
        amount=amount,
        currency="INR",
        payment_type=PaymentType.BOOKING_ADVANCE,
        status=PaymentRecordStatus.SUCCESS,
        signature_verified=True,
        provider_payload={"method": method, "reference": reference, "payment_date": payment_date.isoformat(), "note": note},
        idempotency_key=f"lead-manual-{lead.id}-{reference or timezone.now().timestamp()}",
        paid_at=timezone.now(),
    )
    booking.advance_paid += amount
    booking.balance_due = max(Decimal("0.00"), booking.total_amount - booking.advance_paid)
    booking.payment_status = BookingPaymentStatus.PAID if booking.balance_due == Decimal("0.00") else BookingPaymentStatus.PARTIALLY_PAID
    booking.save(update_fields=["advance_paid", "balance_due", "payment_status", "updated_at"])

    previous = {"payment_status": lead.payment_status, "funnel_status": lead.funnel_status}
    lead.payment_status = LeadPaymentStatus.PAID
    lead.funnel_status = LeadFunnelStatus.PAID
    lead.last_activity_at = timezone.now()
    lead.save(update_fields=["payment_status", "funnel_status", "last_activity_at", "updated_at"])
    record_lead_activity(
        lead=lead,
        action=LeadActivityAction.MANUAL_PAYMENT_RECORDED,
        previous_value=previous,
        new_value={"amount": str(amount), "method": method, "payment_id": str(payment.id)},
        note=note or reference,
        performed_by=performed_by,
        request=request,
    )
    return lead, payment


def record_lead_activity(*, lead, action, previous_value=None, new_value=None, note="", performed_by=None, request=None):
    return LeadActivity.objects.create(
        lead=lead,
        action=action,
        previous_value=previous_value or {},
        new_value=new_value or {},
        note=note,
        performed_by=performed_by,
        ip_address=_ip_address(request),
    )


def _max_funnel_status(current, candidate):
    return candidate if FUNNEL_RANK[candidate] > FUNNEL_RANK[current] else current


def _max_payment_status(current, candidate):
    return candidate if PAYMENT_RANK[candidate] > PAYMENT_RANK[current] else current


def _customer_name(user):
    profile = getattr(user, "customer_profile", None)
    display_name = getattr(profile, "display_name", "")
    return display_name or " ".join(part for part in [user.first_name, user.last_name] if part) or user.phone_number


def _address_text(snapshot):
    return ", ".join(
        str(part)
        for part in [
            snapshot.get("address_line_1"),
            snapshot.get("address_line_2"),
            snapshot.get("locality"),
            snapshot.get("city"),
            snapshot.get("postal_code"),
        ]
        if part
    )


def _lead_payment_url(lead):
    app_url = getattr(settings, "FRONTEND_APP_URL", "") or "https://purplesquad.netlify.app"
    if lead.converted_booking_id:
        return f"{app_url.rstrip('/')}/book/pay/{lead.converted_booking_id}"
    return f"{app_url.rstrip('/')}/support?lead={lead.id}"


def _ip_address(request):
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
