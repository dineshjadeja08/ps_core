from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.catalogue.models import APP_CATEGORY_CHOICES, Service, ServiceCategory
from apps.catalogue.serializers import ServiceListSerializer
from apps.locations.models import ServiceArea


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
    service = create_service(
        ac_category,
        whats_included="Filter cleaning\nCooling test",
        landing_group="Repair & Services",
    )

    response = client.get("/api/v1/services/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["results"][0]["slug"] == service.slug
    assert payload["results"][0]["whats_included"] == "Filter cleaning\nCooling test"
    assert payload["results"][0]["landing_group"] == "Repair & Services"
    assert "landing_thumbnail" in payload["results"][0]
    assert "popup_cover_image" in payload["results"][0]
    assert "popup_content_image" in payload["results"][0]
    assert "list_image" in payload["results"][0]


@pytest.mark.django_db
def test_service_listing_uses_saved_display_order(client, ac_category):
    second = create_service(ac_category, name="Alphabetically First", slug="alphabetically-first", display_order=2)
    first = create_service(ac_category, name="Alphabetically Last", slug="alphabetically-last", display_order=1)

    response = client.get("/api/v1/services/")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["results"]] == [str(first.id), str(second.id)]


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
def test_mobile_app_fields_are_public_and_filterable(client, ac_category):
    mobile_service = create_service(
        ac_category,
        name="Mobile AC Service",
        slug="mobile-ac-service",
        show_in_app=True,
        app_category="ac",
    )
    create_service(ac_category, name="Website Only Service", slug="website-only-service")

    listing = client.get("/api/v1/services/")
    mobile_listing = client.get("/api/v1/services/?show_in_app=true")
    website_listing = client.get("/api/v1/services/?show_in_app=false")
    detail = client.get(f"/api/v1/services/{mobile_service.slug}/")

    assert listing.status_code == mobile_listing.status_code == website_listing.status_code == detail.status_code == 200
    assert all("show_in_app" in item and "app_category" in item for item in listing.json()["results"])
    assert [item["slug"] for item in mobile_listing.json()["results"]] == [mobile_service.slug]
    assert [item["slug"] for item in website_listing.json()["results"]] == ["website-only-service"]
    assert mobile_listing.json()["results"][0]["app_category"] == "ac"
    assert detail.json()["show_in_app"] is True
    assert detail.json()["app_category"] == "ac"
    assert client.get("/api/v1/services/?show_in_app=maybe").status_code == 400


@pytest.mark.django_db
def test_app_category_rejects_values_outside_configured_choices(ac_category):
    with pytest.raises(ValidationError):
        create_service(ac_category, app_category="not-a-mobile-category")


def test_app_category_serializer_documents_the_complete_ordered_enum():
    serializer_choices = list(ServiceListSerializer().fields["app_category"].choices.items())
    assert serializer_choices == list(APP_CATEGORY_CHOICES)


@pytest.mark.django_db
def test_service_filtering(client, ac_category, repair_category):
    create_service(ac_category, name="AC General Service", slug="ac-general-service", is_featured=True, is_popular=True)
    create_service(
        repair_category,
        name="AC Noise Repair",
        slug="ac-noise-repair",
        is_featured=False,
    )

    by_category = client.get("/api/v1/services/?category=ac-repair")
    by_featured = client.get("/api/v1/services/?featured=true")
    by_popular = client.get("/api/v1/services/?is_popular=true")
    by_search = client.get("/api/v1/services/?search=noise")

    assert [item["slug"] for item in by_category.json()["results"]] == ["ac-noise-repair"]
    assert [item["slug"] for item in by_featured.json()["results"]] == ["ac-general-service"]
    assert [item["slug"] for item in by_popular.json()["results"]] == ["ac-general-service"]
    assert [item["slug"] for item in by_search.json()["results"]] == ["ac-noise-repair"]


@pytest.mark.django_db
def test_service_filtering_by_active_city(client, ac_category):
    chennai_service = create_service(ac_category, name="Chennai AC", slug="chennai-ac")
    other_service = create_service(ac_category, name="Other AC", slug="other-ac")
    chennai = ServiceArea.objects.create(name="Anna Nagar", city="Chennai", state="Tamil Nadu", postal_code="600040")
    coimbatore = ServiceArea.objects.create(name="Peelamedu", city="Coimbatore", state="Tamil Nadu", postal_code="641004")
    chennai.services.add(chennai_service)
    coimbatore.services.add(other_service)

    response = client.get("/api/v1/services/?city=Chennai")

    assert response.status_code == 200
    assert [item["slug"] for item in response.json()["results"]] == ["chennai-ac"]


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
