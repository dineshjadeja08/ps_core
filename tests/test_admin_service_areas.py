from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.catalogue.models import Service, ServiceCategory
from apps.locations.models import ServiceArea


@pytest.fixture
def admin_client():
    user = User.objects.create_user("+919876543299", role=UserRole.ADMIN, is_verified=True, is_staff=True)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def services():
    category = ServiceCategory.objects.create(name="AC", slug="ac", display_order=1)
    return [
        Service.objects.create(
            category=category,
            name=name,
            slug=slug,
            base_price=Decimal("500.00"),
            advance_amount=Decimal("100.00"),
            estimated_duration_minutes=60,
        )
        for name, slug in (("AC Check-up", "ac-check-up"), ("Gas Refill", "gas-refill"))
    ]


@pytest.mark.django_db
def test_admin_can_create_and_update_services_available_by_pincode(admin_client, services):
    create = admin_client.post(
        "/api/v1/admin/service-areas/",
        {
            "name": "Central",
            "city": "Chennai",
            "state": "Tamil Nadu",
            "country": "India",
            "postal_code": "600 001",
            "service_ids": [str(services[0].id)],
            "is_active": True,
        },
        format="json",
    )

    assert create.status_code == 201
    area = ServiceArea.objects.get(id=create.json()["id"])
    assert area.postal_code == "600001"
    assert area.services_configured is True
    assert list(area.services.values_list("id", flat=True)) == [services[0].id]

    update = admin_client.patch(
        f"/api/v1/admin/service-areas/{area.id}/",
        {"service_ids": [str(services[1].id)]},
        format="json",
    )

    assert update.status_code == 200
    assert update.json()["services"] == [{"id": str(services[1].id), "name": "Gas Refill", "slug": "gas-refill"}]


@pytest.mark.django_db
def test_public_service_list_respects_configured_pincode_coverage(client, services):
    area = ServiceArea.objects.create(
        name="Central",
        city="Chennai",
        state="Tamil Nadu",
        postal_code="600001",
        services_configured=True,
    )
    area.services.add(services[1])

    response = client.get("/api/v1/services/?postal_code=600001")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["results"]] == [str(services[1].id)]
