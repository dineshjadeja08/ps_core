from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.catalogue.models import Service, ServiceCategory
from apps.locations.models import ServiceArea
from apps.scheduling.models import TimeSlot
from apps.scheduling.services import lock_slot_for_reservation


@pytest.fixture
def service_area():
    return ServiceArea.objects.create(
        name="Tirupattur Central",
        city="Tirupattur",
        state="Tamil Nadu",
        postal_code="635601",
    )


@pytest.fixture
def service():
    category = ServiceCategory.objects.create(name="AC Service", slug="ac-service")
    return Service.objects.create(
        category=category,
        name="AC General Service",
        slug="ac-general-service",
        base_price=Decimal("1499.00"),
        advance_amount=Decimal("299.00"),
        estimated_duration_minutes=90,
    )


def create_slot(service_area, **overrides):
    tomorrow = timezone.localdate() + timedelta(days=1)
    data = {
        "service_area": service_area,
        "date": tomorrow,
        "start_time": time(10, 0),
        "end_time": time(12, 0),
        "capacity": 2,
        "is_active": True,
    }
    data.update(overrides)
    return TimeSlot.objects.create(**data)


@pytest.mark.django_db
def test_available_slots(client, service, service_area):
    slot = create_slot(service_area)

    response = client.get(
        f"/api/v1/slots/?service_id={service.id}&date={slot.date}&postal_code=635601"
    )

    assert response.status_code == 200
    assert any(item["id"] == str(slot.id) for item in response.json())
    assert next(item for item in response.json() if item["id"] == str(slot.id))["available_capacity"] == 2


@pytest.mark.django_db
def test_slots_are_created_for_supported_days(client, service, service_area):
    service_date = timezone.localdate() + timedelta(days=3)

    response = client.get(
        f"/api/v1/slots/?service_id={service.id}&date={service_date}&postal_code=635601"
    )

    assert response.status_code == 200
    assert len(response.json()) == 6
    assert response.json()[0]["start_time"] == "08:00:00"
    assert response.json()[-1]["end_time"] == "20:00:00"


@pytest.mark.django_db
def test_full_slot(client, service, service_area, monkeypatch):
    slot = create_slot(service_area, capacity=1)
    monkeypatch.setattr("apps.scheduling.services.count_reserved_bookings", lambda slot: 1)

    response = client.get(
        f"/api/v1/slots/?service_id={service.id}&date={slot.date}&postal_code=635601"
    )

    assert response.status_code == 200
    assert all(item["id"] != str(slot.id) for item in response.json())
    assert len(response.json()) == 5


@pytest.mark.django_db
def test_inactive_slot(client, service, service_area):
    slot = create_slot(service_area, is_active=False)

    response = client.get(
        f"/api/v1/slots/?service_id={service.id}&date={slot.date}&postal_code=635601"
    )

    assert response.status_code == 200
    assert all(item["id"] != str(slot.id) for item in response.json())
    assert len(response.json()) == 5


@pytest.mark.django_db
def test_past_slot(client, service, service_area):
    slot = create_slot(service_area, date=timezone.localdate() - timedelta(days=1))

    response = client.get(
        f"/api/v1/slots/?service_id={service.id}&date={slot.date}&postal_code=635601"
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.django_db
def test_unsupported_area(client, service):
    response = client.get(
        f"/api/v1/slots/?service_id={service.id}&date={timezone.localdate() + timedelta(days=1)}&postal_code=000000"
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ADDRESS_OUTSIDE_SERVICE_AREA"


@pytest.mark.django_db
def test_capacity_behavior(service_area):
    slot = create_slot(service_area, capacity=1)

    locked = lock_slot_for_reservation(slot.id)

    assert locked.id == slot.id


@pytest.mark.django_db
def test_slot_validation(service_area):
    with pytest.raises(ValidationError):
        create_slot(service_area, start_time=time(12, 0), end_time=time(10, 0))

    with pytest.raises(ValidationError):
        create_slot(service_area, start_time=time(13, 0), end_time=time(14, 0), capacity=0)
