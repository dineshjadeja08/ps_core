from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import UserRole
from apps.bookings.models import BookingStatus, PaymentStatus
from apps.bookings.services import generate_booking_number
from apps.operations.models import LeadFunnelStatus, LeadStatus
from apps.operations.services import link_booking_to_lead, mark_booking_payment_paid
from apps.payments.models import Payment, PaymentProvider, PaymentRecordStatus, PaymentType
from tests.factories import address_factory, booking_factory, service_area_factory, service_factory, slot_factory, user_factory


@pytest.mark.django_db
def test_booking_number_serial_is_month_scoped():
    assert generate_booking_number(for_date=date(2026, 9, 1)) == "PS26090001"
    assert generate_booking_number(for_date=date(2026, 9, 30)) == "PS26090002"
    assert generate_booking_number(for_date=date(2026, 10, 1)) == "PS26100001"


@pytest.mark.django_db
def test_payment_converts_lead_and_exposes_work_order():
    admin = user_factory("+919641000001", role=UserRole.ADMIN, is_staff=True)
    customer = user_factory("+919641000002")
    service = service_factory()
    area = service_area_factory()
    address = address_factory(customer)
    slot = slot_factory(area)
    booking = booking_factory(
        customer,
        service,
        address,
        slot,
        booking_number="PS26090042",
        booking_status=BookingStatus.CONFIRMED,
        payment_status=PaymentStatus.PARTIALLY_PAID,
    )
    lead = link_booking_to_lead(booking=booking)
    payment = Payment.objects.create(
        booking=booking,
        provider=PaymentProvider.OFFLINE,
        amount=Decimal("299.00"),
        payment_type=PaymentType.BOOKING_ADVANCE,
        status=PaymentRecordStatus.SUCCESS,
        paid_at=timezone.now(),
    )

    assert lead.status == LeadStatus.NEW
    assert lead.pending_booking == booking
    assert lead.converted_booking is None

    converted = mark_booking_payment_paid(booking=booking, payment=payment)
    converted.refresh_from_db()
    assert converted.status == LeadStatus.CONVERTED
    assert converted.funnel_status == LeadFunnelStatus.PAID
    assert converted.pending_booking is None
    assert converted.converted_booking == booking

    client = APIClient()
    client.force_authenticate(admin)
    response = client.get("/api/v1/admin/work-orders/")

    assert response.status_code == 200
    assert response.json()["count"] == 1
    item = response.json()["results"][0]
    assert item["booking_number"] == "PS26090042"
    assert item["customer_phone"] == customer.phone_number
    assert item["paid_at"] is not None


@pytest.mark.django_db
def test_work_orders_exclude_unpaid_bookings():
    admin = user_factory("+919641000003", role=UserRole.ADMIN, is_staff=True)
    customer = user_factory("+919641000004")
    service = service_factory()
    area = service_area_factory()
    booking_factory(customer, service, address_factory(customer), slot_factory(area), booking_number="PS26090043")
    client = APIClient()
    client.force_authenticate(admin)

    response = client.get("/api/v1/admin/work-orders/")

    assert response.status_code == 200
    assert response.json()["count"] == 0
