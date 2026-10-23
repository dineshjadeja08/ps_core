from decimal import Decimal
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from apps.audit.models import AuditAction
from apps.audit.services import audit_event
from apps.bookings.models import Booking, PaymentStatus as BookingPaymentStatus
from apps.bookings.models import BookingStatus, BookingStatusHistory
from apps.bookings.services import create_booking
from apps.accounts.models import CustomerProfile, User, UserRole
from apps.catalogue.models import Service
from apps.locations.models import Address, ServiceArea
from apps.notifications.models import Notification, NotificationChannel, NotificationEvent
from apps.notifications.services import notification_event_enabled, send_notification
from apps.operations.models import (
    ACTIVE_LEAD_STATUSES,
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
from apps.scheduling.models import TimeSlot
from apps.scheduling.services import get_available_capacity, is_slot_expired

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


def mark_cart_added(*, customer, service, request=None):
    return upsert_lead(
        customer=customer,
        mobile_number=customer.phone_number,
        customer_name=_customer_name(customer),
        service=service,
        source=LeadSource.CART,
        funnel_status=LeadFunnelStatus.CART_ADDED,
        payment_status=LeadPaymentStatus.NOT_REQUIRED,
        action=LeadActivityAction.ADDED_TO_CART,
        request=request,
        note="Authenticated customer added service to cart.",
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
    lead.pending_booking = booking
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
            "pending_booking",
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
    lead = Lead.objects.filter(Q(pending_booking=booking) | Q(converted_booking=booking)).order_by("-updated_at").first()
    if not lead:
        lead = link_booking_to_lead(booking=booking)
    if lead.source in {LeadSource.ONCALL, LeadSource.ADMIN, LeadSource.PHONE_CALL, LeadSource.PHONE, LeadSource.MANUAL} and not booking.is_manual_work_order:
        booking.is_manual_work_order = True
        booking.save(update_fields=["is_manual_work_order", "updated_at"])
    previous = {
        "status": lead.status,
        "payment_status": lead.payment_status,
        "funnel_status": lead.funnel_status,
    }
    previous_status = lead.status
    lead.status = LeadStatus.CONVERTED
    lead.converted_booking = booking
    lead.pending_booking = None
    lead.payment_status = LeadPaymentStatus.PAID
    lead.funnel_status = LeadFunnelStatus.PAID
    lead.last_activity_at = timezone.now()
    lead.save(
        update_fields=[
            "status",
            "converted_booking",
            "pending_booking",
            "payment_status",
            "funnel_status",
            "last_activity_at",
            "updated_at",
        ]
    )
    if previous_status != LeadStatus.CONVERTED:
        from apps.operations.models import LeadStatusHistory

        LeadStatusHistory.objects.create(
            lead=lead,
            from_status=previous_status,
            to_status=LeadStatus.CONVERTED,
            changed_by=performed_by,
            notes=f"Payment confirmed for work order {booking.booking_number}.",
        )
    record_lead_activity(
        lead=lead,
        action=LeadActivityAction.PAYMENT_CONFIRMED,
        previous_value=previous,
        new_value={
            "status": lead.status,
            "payment_status": lead.payment_status,
            "funnel_status": lead.funnel_status,
            "payment_id": str(payment.id) if payment else "",
        },
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
            status__in=ACTIVE_LEAD_STATUSES,
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
    lead.customer_name = customer_name or lead.customer_name or mobile_number
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
def send_lead_payment_link(*, lead, performed_by, request=None, channel=NotificationChannel.SMS, payment_scope="ADVANCE"):
    if lead.payment_status == LeadPaymentStatus.PAID:
        raise serializers.ValidationError("Lead is already paid.")
    amount = _lead_full_payment_amount(lead) if payment_scope == "FULL" else lead.advance_amount
    if amount is None and payment_scope == "ADVANCE" and lead.required_service_id:
        amount = lead.required_service.advance_amount
    if not amount or amount <= Decimal("0.00"):
        raise serializers.ValidationError(f"Lead does not have a valid {payment_scope.lower()} amount.")
    if lead.pending_booking_id is None and lead.converted_booking_id is None:
        if not lead.preferred_time_slot_id:
            raise serializers.ValidationError("Choose an available date and time before sending a payment link.")
        booking = _create_pending_lead_booking(lead)
        lead.refresh_from_db()
        lead.pending_booking = booking
    if lead.pending_booking_id:
        lead.pending_booking.advance_required = min(amount, lead.pending_booking.total_amount)
        lead.pending_booking.balance_due = max(lead.pending_booking.total_amount - lead.pending_booking.advance_paid, Decimal("0.00"))
        lead.pending_booking.save(update_fields=["advance_required", "balance_due", "updated_at"])
    provider_id = f"lead-link-{lead.id}-{payment_scope.lower()}-{channel.lower()}"
    if lead.payment_link_expires_at and lead.payment_link_expires_at > timezone.now() and lead.payment_link_url and lead.payment_link_provider_id == provider_id:
        return lead, False

    expires_at = timezone.now() + timezone.timedelta(hours=getattr(settings, "LEAD_PAYMENT_LINK_EXPIRY_HOURS", 24))
    lead.payment_link_provider_id = provider_id
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
        note=f"{payment_scope.title()} payment link created for unpaid lead.",
    )
    if channel == NotificationChannel.WHATSAPP or notification_event_enabled(NotificationEvent.PAYMENT_PENDING):
        notification = Notification.objects.create(
            recipient=lead.customer,
            booking=lead.converted_booking or lead.pending_booking,
            event=NotificationEvent.PAYMENT_PENDING,
            channel=channel,
            title="Payment link",
            message=f"Purple Squad {payment_scope.lower()} payment link for ₹{amount}: {lead.payment_link_url}",
            payload={
                "lead_id": str(lead.id),
                "payment_link_url": lead.payment_link_url,
                "payment_scope": payment_scope,
                "amount": str(amount),
                "mobile": lead.primary_mobile,
                "lead_payment_link": True,
                "template_values": [lead.customer_name, str(amount), lead.payment_link_url],
            },
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
def convert_lead_to_work_order(*, lead, performed_by, booking=None, notes=""):
    # PostgreSQL cannot lock the nullable related rows included by these outer joins.
    lead = Lead.objects.select_for_update(of=("self",)).select_related("pending_booking", "required_service").get(pk=lead.pk)
    if lead.status == LeadStatus.CONVERTED and lead.converted_booking_id:
        return lead

    booking = booking or lead.pending_booking
    create_from_lead = booking is None
    if booking is not None:
        if lead.required_service_id and booking.service_id != lead.required_service_id:
            raise serializers.ValidationError(
                {"booking_id": ["The booking service does not match the lead service."]}
            )

    if create_from_lead:
        if not lead.required_service_id:
            raise serializers.ValidationError("Select a service before creating a work order.")
        if not lead.preferred_date or not lead.preferred_slot:
            raise serializers.ValidationError("Schedule the lead before creating a work order.")
        if not lead.address or not lead.city or not lead.pincode:
            raise serializers.ValidationError("A complete service address is required.")

        service_area = ServiceArea.objects.filter(postal_code=lead.pincode, is_active=True).first()
        if service_area is None:
            raise serializers.ValidationError("The lead pincode is outside the active service area.")
        if not service_area.supports_service(lead.required_service):
            raise serializers.ValidationError("The selected service is not available at this pincode.")

        customer, created = User.objects.get_or_create(
            phone_number=lead.primary_mobile,
            defaults={"role": UserRole.CUSTOMER, "is_active": True, "is_verified": True},
        )
        if created:
            customer.set_unusable_password()
            customer.save(update_fields=["password", "updated_at"])
        CustomerProfile.objects.get_or_create(user=customer, defaults={"display_name": lead.customer_name})
        address, _ = Address.objects.get_or_create(
            customer=customer,
            phone=lead.primary_mobile,
            address_line_1=lead.address,
            postal_code=lead.pincode,
            defaults={
                "label": "Lead address",
                "recipient_name": lead.customer_name,
                "city": lead.city,
                "state": service_area.state,
                "country": service_area.country,
                "is_default": not customer.addresses.exists(),
            },
        )
        slot = lead.preferred_time_slot
        if not slot or slot.service_area_id != service_area.id or slot.date != lead.preferred_date:
            raise serializers.ValidationError({"preferred_slot": ["The scheduled time is invalid or unavailable. Select an available site time slot before creating a work order."]})
        booking = create_booking(
            customer=customer,
            service_id=lead.required_service_id,
            address_id=address.id,
            slot_id=slot.id,
            problem_description=lead.customer_notes,
            customer_notes=notes,
            contact_phone=lead.primary_mobile,
        )

    previous_booking_status = booking.booking_status
    booking_update_fields = ["is_manual_work_order", "booking_status", "updated_at"]
    if create_from_lead and lead.quoted_amount is not None:
        booking.subtotal = lead.quoted_amount
        booking.discount_amount = Decimal("0.00")
        booking.training_fee = lead.required_service.training_fee
        booking.tax_amount = Decimal("0.00")
        booking.total_amount = booking.subtotal + booking.training_fee
        if lead.advance_amount is not None:
            booking.advance_required = min(lead.advance_amount, booking.total_amount)
        booking.balance_due = booking.total_amount
        booking_update_fields.extend(["subtotal", "discount_amount", "training_fee", "tax_amount", "total_amount", "advance_required", "balance_due"])
    booking.is_manual_work_order = True
    booking.booking_status = BookingStatus.CONFIRMED
    booking.save(update_fields=booking_update_fields)
    if previous_booking_status != BookingStatus.CONFIRMED:
        BookingStatusHistory.objects.create(
            booking=booking,
            from_status=previous_booking_status,
            to_status=BookingStatus.CONFIRMED,
            changed_by=performed_by,
            notes=notes or "Work order created from lead by admin.",
        )

    previous_status = lead.status
    lead.customer = booking.customer
    lead.status = LeadStatus.CONVERTED
    lead.funnel_status = LeadFunnelStatus.BOOKED
    lead.converted_booking = booking
    lead.pending_booking = None
    lead.internal_notes = "\n".join(part for part in [lead.internal_notes, notes] if part)
    lead.last_activity_at = timezone.now()
    lead.save(update_fields=["customer", "status", "funnel_status", "converted_booking", "pending_booking", "internal_notes", "last_activity_at", "updated_at"])
    if previous_status != LeadStatus.CONVERTED:
        from apps.operations.models import LeadStatusHistory
        LeadStatusHistory.objects.create(
            lead=lead,
            from_status=previous_status,
            to_status=LeadStatus.CONVERTED,
            changed_by=performed_by,
            notes=notes or f"Work order {booking.booking_number} created.",
        )
    return lead


@transaction.atomic
def update_lead_quote(lead):
    """Keep the lead's persisted quote and advance in sync with selected service quantities."""
    items = lead.service_items or ([{"service_id": str(lead.required_service_id), "quantity": 1}] if lead.required_service_id else [])
    services = {str(key): service for key, service in Service.objects.filter(
        id__in=[item.get("service_id") for item in items]
    ).in_bulk().items()}
    subtotal = Decimal("0.00")
    training = Decimal("0.00")
    advance = Decimal("0.00")
    for item in items:
        service = services.get(str(item.get("service_id")))
        quantity = int(item.get("quantity", 1))
        if not service:
            continue
        subtotal += service.effective_price * quantity
        training += service.training_fee * (quantity if service.training_fee_per_unit else 1)
        advance += service.advance_amount * quantity
    total = subtotal + training
    lead.quoted_amount = subtotal
    lead.advance_amount = min(advance, total) if total else Decimal("0.00")
    lead.balance_amount = max(total - lead.advance_amount, Decimal("0.00"))
    lead.save(update_fields=["quoted_amount", "advance_amount", "balance_amount", "updated_at"])
    return lead


def _create_pending_lead_booking(lead):
    if not lead.required_service_id:
        raise serializers.ValidationError("Select a service before creating a payment link.")
    if not lead.address or not lead.city or not lead.pincode:
        raise serializers.ValidationError("Select a complete address from the address suggestions before creating a payment link.")
    customer = lead.customer
    if customer is None:
        customer, created = User.objects.get_or_create(
            phone_number=lead.primary_mobile,
            defaults={"role": UserRole.CUSTOMER, "is_active": True, "is_verified": True},
        )
        if created:
            customer.set_unusable_password()
            customer.save(update_fields=["password", "updated_at"])
        lead.customer = customer
        lead.save(update_fields=["customer", "updated_at"])
    CustomerProfile.objects.get_or_create(user=customer, defaults={"display_name": lead.customer_name})
    area = ServiceArea.objects.filter(postal_code=lead.pincode, is_active=True).first()
    slot = lead.preferred_time_slot
    if not area or not slot or slot.service_area_id != area.id or slot.date != lead.preferred_date:
        raise serializers.ValidationError("The scheduled slot is no longer valid for this address.")
    if not slot.is_active or is_slot_expired(slot) or get_available_capacity(slot) < 1:
        raise serializers.ValidationError("The selected slot is no longer available. Choose another time.")
    items = lead.service_items or [{"service_id": str(lead.required_service_id), "quantity": 1}]
    selected_services = Service.objects.filter(id__in=[item.get("service_id") for item in items], is_active=True, category__is_active=True)
    if len(selected_services) != len(items) or any(not area.supports_service(service) for service in selected_services):
        raise serializers.ValidationError("One or more selected services are not available in this area.")
    address, _ = Address.objects.get_or_create(
        customer=customer,
        phone=lead.primary_mobile,
        address_line_1=lead.address,
        postal_code=lead.pincode,
        defaults={
            "label": "Lead address",
            "recipient_name": lead.customer_name,
            "city": lead.city,
            "state": area.state,
            "country": area.country,
            "is_default": not customer.addresses.exists(),
        },
    )
    booking = create_booking(
        customer=customer,
        service_id=lead.required_service_id,
        address_id=address.id,
        slot_id=slot.id,
        problem_description="Additional requested services: " + ", ".join(
            f"{service.name} × {next(int(item.get('quantity', 1)) for item in items if str(item.get('service_id')) == str(service.id))}"
            for service in selected_services if service.id != lead.required_service_id
        ),
        contact_phone=lead.primary_mobile,
    )
    # One booking/work order can carry multiple requested service lines while preserving
    # the primary service association required by existing assignment and scheduling APIs.
    subtotal, training, total = _lead_booking_totals(lead, selected_services)
    advance = lead.advance_amount or booking.advance_required
    booking.subtotal = subtotal
    booking.discount_amount = Decimal("0.00")
    booking.training_fee = training
    booking.tax_amount = Decimal("0.00")
    booking.total_amount = total
    booking.advance_required = min(advance, total)
    booking.balance_due = total
    booking.save(update_fields=["subtotal", "discount_amount", "training_fee", "tax_amount", "total_amount", "advance_required", "balance_due", "updated_at"])
    lead.refresh_from_db()
    update_lead_quote(lead)
    return booking


def _lead_booking_totals(lead, selected_services):
    items = lead.service_items or [{"service_id": str(lead.required_service_id), "quantity": 1}]
    services = {str(service.id): service for service in selected_services}
    subtotal = training = Decimal("0.00")
    for item in items:
        service = services[str(item["service_id"])]
        quantity = int(item.get("quantity", 1))
        subtotal += service.effective_price * quantity
        training += service.training_fee * (quantity if service.training_fee_per_unit else 1)
    return subtotal, training, subtotal + training


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
    booking_id = lead.converted_booking_id or lead.pending_booking_id
    if booking_id:
        return f"{app_url.rstrip('/')}/book/pay/{booking_id}"
    return f"{app_url.rstrip('/')}/support?lead={lead.id}"


def _lead_full_payment_amount(lead):
    if lead.service_items:
        items = lead.service_items
        services = {str(key): service for key, service in Service.objects.filter(
            id__in=[item.get("service_id") for item in items]
        ).in_bulk().items()}
        subtotal = training_fee = Decimal("0.00")
        for item in items:
            service = services.get(str(item.get("service_id")))
            if not service:
                continue
            quantity = int(item.get("quantity", 1))
            subtotal += service.effective_price * quantity
            training_fee += service.training_fee * (quantity if service.training_fee_per_unit else 1)
        return subtotal + training_fee
    subtotal = lead.quoted_amount
    if subtotal is None and lead.required_service_id:
        subtotal = lead.required_service.effective_price
    training_fee = lead.required_service.training_fee if lead.required_service_id else Decimal("0.00")
    return (subtotal or Decimal("0.00")) + (training_fee or Decimal("0.00"))


def _ip_address(request):
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
