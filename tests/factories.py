from datetime import time, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.bookings.models import Booking, BookingStatus, PaymentStatus
from apps.catalogue.models import Service, ServiceCategory
from apps.locations.models import Address, ServiceArea
from apps.scheduling.models import TimeSlot
from apps.technicians.models import TechnicianAvailabilityStatus, TechnicianProfile, TechnicianSkill, TechnicianVerificationStatus


def user_factory(phone_number, *, role=UserRole.CUSTOMER, **overrides):
    defaults = {"is_verified": True}
    defaults.update(overrides)
    return User.objects.create_user(phone_number, role=role, **defaults)


def service_area_factory(*, postal_code="635601", name="Tirupattur Central"):
    return ServiceArea.objects.create(
        name=name,
        city="Tirupattur",
        state="Tamil Nadu",
        postal_code=postal_code,
    )


def service_factory(*, category=None, slug="ac-general-service"):
    category = category or ServiceCategory.objects.create(name="AC Service", slug="ac-service")
    return Service.objects.create(
        category=category,
        name="AC General Service",
        slug=slug,
        base_price=Decimal("1499.00"),
        advance_amount=Decimal("299.00"),
        estimated_duration_minutes=90,
    )


def address_factory(customer, *, postal_code="635601"):
    return Address.objects.create(
        customer=customer,
        label="Home",
        recipient_name="Dinesh",
        phone="+919876543210",
        address_line_1="12 Main Road",
        city="Tirupattur",
        state="Tamil Nadu",
        postal_code=postal_code,
    )


def slot_factory(service_area, *, days=2, start_hour=10, capacity=2):
    return TimeSlot.objects.create(
        service_area=service_area,
        date=timezone.localdate() + timedelta(days=days),
        start_time=time(start_hour, 0),
        end_time=time(start_hour + 2, 0),
        capacity=capacity,
    )


def booking_factory(customer, service, address, slot, **overrides):
    data = {
        "booking_number": f"PS-FLOW{Booking.objects.count() + 1:03d}",
        "customer": customer,
        "service": service,
        "address": address,
        "address_snapshot": {"postal_code": address.postal_code},
        "service_date": slot.date,
        "time_slot": slot,
        "problem_description": "AC is not cooling.",
        "subtotal": Decimal("1499.00"),
        "total_amount": Decimal("1499.00"),
        "advance_required": Decimal("299.00"),
        "advance_paid": Decimal("299.00"),
        "balance_due": Decimal("1200.00"),
        "balance_collected": Decimal("0.00"),
        "booking_status": BookingStatus.CONFIRMED,
        "payment_status": PaymentStatus.PARTIALLY_PAID,
    }
    data.update(overrides)
    return Booking.objects.create(**data)


def technician_factory(*, phone_number="+919876543300", code="TECH-FLOW", service_area=None):
    user = user_factory(phone_number, role=UserRole.TECHNICIAN)
    skill = TechnicianSkill.objects.create(name=f"AC Skill {code}")
    profile = TechnicianProfile.objects.create(
        user=user,
        employee_code=code,
        display_name=f"Technician {code}",
        phone=phone_number,
        is_active=True,
        is_available=True,
        background_verification_status=TechnicianVerificationStatus.VERIFIED,
        availability_status=TechnicianAvailabilityStatus.AVAILABLE,
    )
    profile.skills.add(skill)
    if service_area is not None:
        profile.service_areas.add(service_area)
    return profile


def booking_payload(service, address, slot, **overrides):
    payload = {
        "service_id": str(service.id),
        "address_id": str(address.id),
        "slot_id": str(slot.id),
        "problem_description": "AC is not cooling properly.",
        "customer_notes": "Please call before arriving.",
    }
    payload.update(overrides)
    return payload
