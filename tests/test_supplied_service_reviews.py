from io import StringIO
from uuid import NAMESPACE_URL, uuid5

import pytest
from django.core.management import call_command

from apps.catalogue.models import Service, ServiceCategory
from apps.reviews.legacy_supplied_reviews import AC_REVIEWS
from apps.reviews.models import Review
from apps.reviews.supplied_reviews import SERVICE_REVIEWS
from tests.factories import address_factory, booking_factory, service_area_factory, slot_factory, user_factory


def create_service(category, name, slug):
    return Service.objects.create(category=category, name=name, slug=slug, base_price=299, advance_amount=99, estimated_duration_minutes=60)


@pytest.mark.django_db
def test_workbook_reviews_go_to_their_named_services():
    category = ServiceCategory.objects.create(name="Appliances", slug="appliances")
    services = {
        name: create_service(category, name, f"review-service-{index}")
        for index, name in enumerate(SERVICE_REVIEWS, start=1)
    }
    tv = create_service(category, "TV Repair", "tv-repair")
    call_command("import_supplied_service_reviews", stdout=StringIO(), stderr=StringIO())
    assert Review.objects.count() == 110
    for name, service in services.items():
        actual = set(Review.objects.filter(service=service).values_list("reviewer_name", "comment", "rating"))
        assert actual == set(SERVICE_REVIEWS[name])
        assert Review.objects.filter(service=service).count() == len(SERVICE_REVIEWS[name])
    assert not Review.objects.filter(service=tv).exists()
    assert not Review.objects.exclude(booking=None, customer=None).exists()


@pytest.mark.django_db
def test_aliases_match_existing_service_names():
    category = ServiceCategory.objects.create(name="Appliances", slug="appliances")
    aliases = [
        ("Full AC Chemical Wash", "full-ac-chemical-wash", "AC Chemical Wash"),
        ("AC Repair & Gas Refill", "ac-repair-gas-refill", "AC Gas Refill"),
        ("Washing Machine Repair & Service", "washing-machine-repair-service", "Washing Machine Repair"),
    ]
    services = [(create_service(category, name, slug), group) for name, slug, group in aliases]
    call_command("import_supplied_service_reviews", stdout=StringIO(), stderr=StringIO())
    for service, group in services:
        assert Review.objects.filter(service=service).count() == len(SERVICE_REVIEWS[group])


@pytest.mark.django_db
def test_replacement_removes_only_legacy_import_and_preserves_real_and_manual_reviews():
    category = ServiceCategory.objects.create(name="AC", slug="ac")
    ac = create_service(category, "AC Installation", "ac-installation")
    name, comment, rating = AC_REVIEWS[0]
    old_id = uuid5(NAMESPACE_URL, f"purplesquad:supplied-reviews:2026-10:{ac.id}:{name}:{comment}")
    Review.objects.create(id=old_id, service=ac, reviewer_name=name, comment="Admin edited old imported text", rating=rating)
    manual = Review.objects.create(service=ac, reviewer_name="Manual", comment="Keep this review", rating=1)
    customer = user_factory("+919321456780")
    address = address_factory(customer)
    slot = slot_factory(service_area_factory())
    booking = booking_factory(customer, ac, address, slot)
    booking_review = Review.objects.create(booking=booking, customer=customer, rating=2, comment="Keep booking feedback")
    preview = StringIO()
    call_command("import_supplied_service_reviews", dry_run=True, stdout=preview, stderr=StringIO())
    assert Review.objects.filter(id=old_id).exists()
    assert "Would remove 1" in preview.getvalue()

    call_command("import_supplied_service_reviews", stdout=StringIO(), stderr=StringIO())
    assert not Review.objects.filter(id=old_id).exists()
    assert Review.objects.filter(id=manual.id).exists()
    assert Review.objects.filter(id=booking_review.id).exists()
    imported = Review.objects.filter(service=ac, booking__isnull=True).exclude(id=manual.id).first()
    imported.is_visible = False
    imported.comment = "Admin-edited workbook review"
    imported.save()
    call_command("import_supplied_service_reviews", stdout=StringIO(), stderr=StringIO())
    imported.refresh_from_db()
    assert imported.is_visible is False
    assert imported.comment == "Admin-edited workbook review"
    assert Review.objects.filter(service=ac).count() == len(SERVICE_REVIEWS["AC Installation"]) + 1
