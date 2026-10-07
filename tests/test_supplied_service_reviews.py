from io import StringIO

import pytest
from django.core.management import call_command

from apps.catalogue.models import Service, ServiceCategory
from apps.reviews.models import Review
from apps.reviews.supplied_reviews import AC_REVIEWS, WASHING_REVIEWS


def create_service(category, name, slug):
    return Service.objects.create(category=category, name=name, slug=slug, base_price=299, advance_amount=99, estimated_duration_minutes=60)


@pytest.mark.django_db
def test_import_supplied_reviews_targets_only_ac_and_washing_services():
    category = ServiceCategory.objects.create(name="Appliances", slug="appliances")
    ac = create_service(category, "AC Repair & Services", "ac-services")
    washing = create_service(category, "Washing Machine Repair", "washing-machine-repair")
    tv = create_service(category, "TV Repair", "tv-repair")
    installation = create_service(category, "AC Installation", "ac-installation")
    removal = create_service(category, "AC Uninstallation", "ac-uninstallation")
    call_command("import_supplied_service_reviews", stdout=StringIO())
    assert Review.objects.filter(service=ac).count() == 5
    assert set(Review.objects.filter(service=ac).values_list("reviewer_name", "comment", "rating")) == set(AC_REVIEWS[:5])
    assert set(Review.objects.filter(service=washing).values_list("reviewer_name", "comment", "rating")) == set(WASHING_REVIEWS)
    assert not Review.objects.filter(service=tv).exists()
    assert Review.objects.filter(service=installation, reviewer_name="Ishwarya", rating=5).exists()
    assert Review.objects.filter(service=removal, reviewer_name="Parthiban", rating=5).exists()
    assert Review.objects.filter(service=removal).count() == 5
    assert not Review.objects.exclude(booking=None, customer=None).exists()


@pytest.mark.django_db
def test_import_is_repeatable_and_preserves_existing_reviews_and_moderation(client):
    category = ServiceCategory.objects.create(name="AC", slug="ac")
    ac = create_service(category, "AC Service", "ac-service")
    existing = Review.objects.create(service=ac, reviewer_name="Existing customer", comment="Keep this review", rating=1)
    call_command("import_supplied_service_reviews", stdout=StringIO())
    imported = Review.objects.filter(service=ac).exclude(id=existing.id).first()
    imported.is_visible = False
    imported.comment = "Admin edited feedback"
    imported.save()
    call_command("import_supplied_service_reviews", stdout=StringIO())
    assert Review.objects.filter(service=ac).count() == 6
    imported.refresh_from_db()
    assert imported.comment == "Admin edited feedback"
    assert imported.is_visible is False
    response = client.get(f"/api/v1/services/{ac.id}/reviews/")
    assert response.status_code == 200
    assert response.json()["count"] == 5
    assert all(not review["is_booking_review"] for review in response.json()["results"])
