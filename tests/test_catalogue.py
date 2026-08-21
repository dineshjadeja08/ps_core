from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.catalogue.models import Service, ServiceCategory


@pytest.fixture
def ac_category():
    return ServiceCategory.objects.create(
        name="AC Service",
        slug="ac-service",
        description="Routine AC services.",
        display_order=1,
    )


@pytest.fixture
def repair_category():
    return ServiceCategory.objects.create(
        name="AC Repair",
        slug="ac-repair",
        description="Repair services.",
        display_order=2,
    )


def create_service(category, **overrides):
    data = {
        "category": category,
        "name": "AC General Service",
        "slug": "ac-general-service",
        "short_description": "Cleaning and inspection.",
        "description": "A complete AC cleaning service.",
        "base_price": Decimal("1499.00"),
        "advance_amount": Decimal("299.00"),
        "estimated_duration_minutes": 90,
        "is_featured": True,
        "is_active": True,
    }
    data.update(overrides)
    return Service.objects.create(**data)


@pytest.mark.django_db
def test_category_listing(client, ac_category):
    ServiceCategory.objects.create(name="Hidden", slug="hidden", is_active=False)

    response = client.get("/api/v1/service-categories/")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["slug"] == ac_category.slug


@pytest.mark.django_db
def test_service_listing(client, ac_category):
    service = create_service(ac_category)

    response = client.get("/api/v1/services/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["results"][0]["slug"] == service.slug


@pytest.mark.django_db
def test_inactive_service_excluded(client, ac_category):
    create_service(ac_category, is_active=False)

    response = client.get("/api/v1/services/")

    assert response.status_code == 200
    assert response.json()["count"] == 0


@pytest.mark.django_db
def test_service_detail(client, ac_category):
    service = create_service(ac_category)

    response = client.get(f"/api/v1/services/{service.slug}/")

    assert response.status_code == 200
    assert response.json()["description"] == "A complete AC cleaning service."


@pytest.mark.django_db
def test_service_filtering(client, ac_category, repair_category):
    create_service(ac_category, name="AC General Service", slug="ac-general-service", is_featured=True)
    create_service(
        repair_category,
        name="AC Noise Repair",
        slug="ac-noise-repair",
        is_featured=False,
    )

    by_category = client.get("/api/v1/services/?category=ac-repair")
    by_featured = client.get("/api/v1/services/?featured=true")
    by_search = client.get("/api/v1/services/?search=noise")

    assert [item["slug"] for item in by_category.json()["results"]] == ["ac-noise-repair"]
    assert [item["slug"] for item in by_featured.json()["results"]] == ["ac-general-service"]
    assert [item["slug"] for item in by_search.json()["results"]] == ["ac-noise-repair"]


@pytest.mark.django_db
def test_price_validation(ac_category):
    with pytest.raises(ValidationError):
        create_service(ac_category, base_price=Decimal("-1.00"))

    with pytest.raises(ValidationError):
        create_service(ac_category, slug="advance-negative", advance_amount=Decimal("-1.00"))

    with pytest.raises(ValidationError):
        create_service(
            ac_category,
            slug="advance-too-high",
            advance_amount=Decimal("1500.00"),
        )
