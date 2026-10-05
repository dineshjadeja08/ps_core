import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from apps.accounts.models import UserRole
from apps.reviews.models import Review
from tests.factories import address_factory, booking_factory, service_area_factory, service_factory, slot_factory, user_factory


pytestmark = pytest.mark.django_db


@pytest.fixture
def service():
    return service_factory()


@pytest.fixture
def admin_client():
    user = user_factory("+919630001001", role=UserRole.ADMIN, is_staff=True)
    user.groups.add(Group.objects.create(name="Catalogue Manager"))
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def review_payload(selected_service, **overrides):
    return {"service": str(selected_service.id), "reviewer_name": "Customer A", "rating": 5,
            "comment": "Punctual and helpful.", "is_visible": True, **overrides}


def test_admin_can_create_edit_hide_and_delete_service_review(admin_client, service):
    response = admin_client.post("/api/v1/admin/reviews/", review_payload(service), format="json")
    assert response.status_code == 201
    data = response.json()
    review = Review.objects.get(id=data["id"])
    assert review.booking_id is None
    assert review.customer_id is None
    assert data["service_name"] == service.name
    assert data["customer"] == {"name": "Customer A"}
    assert data["is_booking_review"] is False
    assert data["booking_number"] == ""
    public = APIClient().get(f"/api/v1/services/{service.id}/reviews/")
    assert public.json()["results"][0]["reviewer_name"] == "Customer A"

    response = admin_client.patch(f"/api/v1/admin/reviews/{review.id}/",
                                  {"comment": "Updated feedback", "rating": 4, "is_visible": False}, format="json")
    assert response.status_code == 200
    review.refresh_from_db()
    assert review.comment == "Updated feedback"
    assert review.rating == 4
    assert APIClient().get(f"/api/v1/services/{service.id}/reviews/").json()["count"] == 0
    assert admin_client.delete(f"/api/v1/admin/reviews/{review.id}/").status_code == 204
    assert not Review.objects.filter(id=review.id).exists()


def test_service_filter_and_public_list_do_not_leak_other_services(admin_client, service):
    other = service_factory(category=service.category, slug="other-service")
    Review.objects.create(service=service, reviewer_name="Local customer", rating=5, comment="First")
    Review.objects.create(service=other, reviewer_name="Other customer", rating=4, comment="Second")
    admin = admin_client.get("/api/v1/admin/reviews/", {"service": str(service.id)})
    assert admin.status_code == 200
    assert admin.json()["count"] == 1
    assert admin.json()["results"][0]["comment"] == "First"
    public = APIClient().get(f"/api/v1/services/{other.id}/reviews/")
    assert public.json()["count"] == 1
    assert public.json()["results"][0]["comment"] == "Second"
    searched = admin_client.get("/api/v1/admin/reviews/", {"search": "Local customer"})
    assert searched.json()["count"] == 1
    assert admin_client.get("/api/v1/admin/reviews/", {"service": "invalid"}).status_code == 400


@pytest.mark.parametrize("field,value", [("service", None), ("reviewer_name", " "), ("comment", " "), ("rating", 0), ("rating", 6)])
def test_invalid_admin_review_is_rejected(admin_client, service, field, value):
    response = admin_client.post("/api/v1/admin/reviews/", review_payload(service, **{field: value}), format="json")
    assert response.status_code == 400
    assert Review.objects.count() == 0


def test_new_review_requires_service_and_reviewer_name(admin_client, service):
    response = admin_client.post("/api/v1/admin/reviews/", {"rating": 5, "comment": "Feedback"}, format="json")
    assert response.status_code == 400
    assert Review.objects.count() == 0


def test_customer_cannot_manage_admin_reviews(service):
    customer = user_factory("+919630001002")
    client = APIClient()
    client.force_authenticate(user=customer)
    review = Review.objects.create(service=service, reviewer_name="Customer", rating=5, comment="Feedback")
    assert client.post("/api/v1/admin/reviews/", review_payload(service), format="json").status_code == 403
    assert client.patch(f"/api/v1/admin/reviews/{review.id}/", {"is_visible": False}, format="json").status_code == 403
    assert client.delete(f"/api/v1/admin/reviews/{review.id}/").status_code == 403


def test_booking_review_keeps_its_original_service(admin_client, service):
    customer = user_factory("+919630001003")
    booking = booking_factory(customer, service, address_factory(customer), slot_factory(service_area_factory()))
    review = Review.objects.create(booking=booking, customer=customer, rating=5, comment="Booking feedback")
    other = service_factory(category=service.category, slug="different-service")
    response = admin_client.get(f"/api/v1/admin/reviews/{review.id}/")
    assert response.status_code == 200
    assert response.json()["is_booking_review"] is True
    assert response.json()["service"] == str(service.id)
    assert admin_client.patch(f"/api/v1/admin/reviews/{review.id}/", {"service": str(other.id)}, format="json").status_code == 400
    assert APIClient().get(f"/api/v1/services/{service.id}/reviews/").json()["count"] == 1


def test_admin_can_move_standalone_review_to_another_service(admin_client, service):
    review = Review.objects.create(service=service, reviewer_name="Customer", rating=5, comment="Feedback")
    other = service_factory(category=service.category, slug="updated-service")
    response = admin_client.patch(f"/api/v1/admin/reviews/{review.id}/", {"service": str(other.id)}, format="json")
    assert response.status_code == 200
    assert APIClient().get(f"/api/v1/services/{service.id}/reviews/").json()["count"] == 0
    assert APIClient().get(f"/api/v1/services/{other.id}/reviews/").json()["count"] == 1
