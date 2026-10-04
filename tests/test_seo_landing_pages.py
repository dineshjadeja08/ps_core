from decimal import Decimal
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.utils import timezone

from apps.catalogue.models import SeoLandingPage, Service, ServiceCategory
from apps.catalogue.seo_keywords import KEYWORD_CLUSTERS, keyword_targets


@pytest.fixture(autouse=True)
def clear_seeded_seo_pages(db):
    SeoLandingPage.objects.all().delete()


def page_values(**overrides):
    values = {
        "service_slug": "ac-service-chennai",
        "service_name": "AC Service",
        "category_slug": "ac-services",
        "city": "Chennai",
        "area": "Velachery",
        "area_slug": "velachery",
        "postal_code": "600042",
        "meta_title": "AC Service in Velachery, Chennai | Purple Squad",
        "meta_description": "Book AC service in Velachery with transparent pricing and doorstep support.",
        "h1": "AC Service & Repair in Velachery, Chennai",
        "primary_keyword": "AC service in Velachery",
        "secondary_keywords": ["AC repair in Velachery", "AC cleaning in Velachery"],
        "supporting_terms": ["doorstep AC service"],
        "search_intent": "Local transactional service booking",
        "content_status": "READY",
        "intro_content": "Purple Squad provides AC cleaning and repair support across active Velachery service pincodes, with pricing shown before booking and any additional work explained before it begins.",
        "coverage_areas": ["Vijaya Nagar", "Baby Nagar"],
        "faqs": [{"question": "Is service available?", "answer": "Availability is checked using the address pincode."}],
        "is_active": True,
        "is_indexable": True,
    }
    values.update(overrides)
    return values


@pytest.mark.django_db
def test_public_seo_page_has_services_and_internal_links(client):
    category = ServiceCategory.objects.create(name="AC", slug="ac-services", is_active=True)
    Service.objects.create(
        category=category,
        name="AC Inspection",
        slug="ac-inspection-test",
        base_price=Decimal("499.00"),
        advance_amount=Decimal("99.00"),
        advance_payment_value=Decimal("99.00"),
        estimated_duration_minutes=60,
        is_active=True,
    )
    SeoLandingPage.objects.create(**page_values(area="", area_slug="", postal_code="", coverage_areas=[]))
    area_page = SeoLandingPage.objects.create(**page_values())
    SeoLandingPage.objects.create(**page_values(area="Tambaram", area_slug="tambaram"))

    response = client.get(f"/api/v1/seo-pages/{area_page.page_slug}/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["path"] == "/ac-service-chennai/velachery"
    assert payload["services"][0]["slug"] == "ac-inspection-test"
    assert payload["parent_page"]["path"] == "/ac-service-chennai"
    assert payload["nearby_pages"][0]["path"] == "/ac-service-chennai/tambaram"
    assert "primary_keyword" not in payload
    assert "secondary_keywords" not in payload


@pytest.mark.django_db
def test_sitemap_feed_only_lists_active_indexable_pages(client):
    visible = SeoLandingPage.objects.create(**page_values())
    SeoLandingPage.objects.create(**page_values(area="Tambaram", area_slug="tambaram", is_indexable=False))
    SeoLandingPage.objects.create(**page_values(area="Pallavaram", area_slug="pallavaram", is_active=False))

    response = client.get("/api/v1/seo-pages/")

    assert response.status_code == 200
    assert [item["page_slug"] for item in response.json()] == [visible.page_slug]


@pytest.mark.django_db
def test_noindex_page_is_retrievable_but_not_listed_and_invalid_page_is_404(client):
    page = SeoLandingPage.objects.create(**page_values(is_indexable=False))

    assert client.get(f"/api/v1/seo-pages/{page.page_slug}/").status_code == 200
    assert client.get("/api/v1/seo-pages/").json() == []
    assert client.get("/api/v1/seo-pages/ac-service-chennai/not-a-real-area/").status_code == 404


@pytest.mark.django_db
def test_indexable_page_can_be_excluded_from_sitemap(client):
    SeoLandingPage.objects.create(**page_values(include_in_sitemap=False))

    assert client.get("/api/v1/seo-pages/").json() == []


@pytest.mark.django_db
def test_future_page_is_not_public_or_linked(client):
    parent = SeoLandingPage.objects.create(**page_values(area="", area_slug="", postal_code="", coverage_areas=[]))
    future_page = SeoLandingPage.objects.create(**page_values(published_at=timezone.now() + timedelta(days=1)))

    response = client.get(f"/api/v1/seo-pages/{parent.page_slug}/")

    assert response.status_code == 200
    assert response.json()["area_pages"] == []
    assert client.get(f"/api/v1/seo-pages/{future_page.page_slug}/").status_code == 404


@pytest.mark.django_db
def test_indexable_area_page_requires_local_content():
    with pytest.raises(ValidationError):
        SeoLandingPage.objects.create(**page_values(intro_content="Too short", coverage_areas=[]))


@pytest.mark.django_db
def test_indexing_requires_editorially_ready_keyword_content():
    with pytest.raises(ValidationError):
        SeoLandingPage.objects.create(**page_values(content_status="NEEDS_REVIEW"))


def test_ac_keyword_cluster_consolidates_related_queries_without_claim_modifiers():
    targets = keyword_targets("ac-service-chennai", "Velachery", "AC Service")

    assert targets["primary_keyword"] == "AC service in Velachery"
    assert "AC repair in Velachery" in targets["secondary_keywords"]
    assert "AC gas refill in Velachery" in targets["secondary_keywords"]
    combined = " ".join([targets["primary_keyword"], *targets["secondary_keywords"]]).lower()
    assert "near me" not in combined
    assert "best" not in combined
    assert "cheapest" not in combined
    assert len(KEYWORD_CLUSTERS) == 13


@pytest.mark.django_db
def test_sync_creates_noindex_area_links_for_every_service_family(client):
    from apps.locations.models import ServiceArea, ServiceAreaLocality

    service_area = ServiceArea.objects.create(
        name="Anna Nagar / Thirumangalam",
        city="Chennai",
        state="Tamil Nadu",
        postal_code="600040",
    )
    ServiceAreaLocality.objects.create(service_area=service_area, name="Anna Nagar", slug="anna-nagar")
    for service_slug, service_name in (("ac-service-chennai", "AC Service"), ("refrigerator-repair-chennai", "Refrigerator Repair")):
        SeoLandingPage.objects.create(**page_values(
            service_slug=service_slug,
            service_name=service_name,
            area="",
            area_slug="",
            postal_code="",
            coverage_areas=[],
        ))

    call_command("sync_seo_area_pages", verbosity=0)

    generated = SeoLandingPage.objects.filter(area_slug="anna-nagar").order_by("service_slug")
    assert generated.count() == 2
    assert all(page.postal_code == "600040" and not page.is_indexable for page in generated)
    assert all(page.primary_keyword.endswith("in Anna Nagar") for page in generated)
    parent_response = client.get("/api/v1/seo-pages/ac-service-chennai/")
    assert parent_response.status_code == 200
    anna_nagar_link = next(
        link for link in parent_response.json()["area_pages"]
        if link["path"] == "/ac-service-chennai/anna-nagar"
    )
    assert anna_nagar_link["postal_code"] == "600040"
    assert all(not item["area"] for item in client.get("/api/v1/seo-pages/").json())
