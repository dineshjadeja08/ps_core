from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import UserRole
from apps.bookings.models import BookingStatus
from apps.reviews.models import Review
from apps.technicians.models import TechnicianLeave
from tests.factories import (
    address_factory,
    booking_factory,
    service_area_factory,
    service_factory,
    slot_factory,
    technician_factory,
    user_factory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def technician():
    return technician_factory()


@pytest.fixture
def technician_client(technician):
    client = APIClient()
    client.force_authenticate(user=technician.user)
    return client


@pytest.fixture
def jobs(technician):
    customer = user_factory("+919876543210", first_name="Ananya")
    area = service_area_factory()
    service = service_factory()
    address = address_factory(customer)
    slot = slot_factory(area, days=0)
    statuses = [BookingStatus.COMPLETED, BookingStatus.COMPLETED, BookingStatus.CANCELLED, BookingStatus.TECHNICIAN_ASSIGNED]
    return [
        booking_factory(customer, service, address, slot, booking_status=status, assigned_technician=technician.user)
        for status in statuses
    ]


def test_profile_returns_own_technician_profile(technician_client, technician):
    response = technician_client.get("/api/v1/technician/profile/")

    assert response.status_code == 200
    assert response.json()["employee_code"] == technician.employee_code


def test_profile_is_404_without_linked_profile():
    client = APIClient()
    client.force_authenticate(user=user_factory("+919876543301", role=UserRole.TECHNICIAN))

    assert client.get("/api/v1/technician/profile/").status_code == 404


def test_self_service_endpoints_reject_customers():
    client = APIClient()
    client.force_authenticate(user=user_factory("+919876543302"))

    for path in ("profile", "reviews", "leaves", "performance"):
        assert client.get(f"/api/v1/technician/{path}/").status_code == 403


def test_reviews_list_only_my_visible_reviews_with_first_name(technician_client, technician, jobs):
    other = technician_factory(phone_number="+919876543303", code="TECH-OTHER")
    Review.objects.create(booking=jobs[0], customer=jobs[0].customer, technician=technician.user, rating=5, comment="Neat work")
    Review.objects.create(booking=jobs[1], customer=jobs[1].customer, technician=other.user, rating=2, comment="Late")
    Review.objects.create(booking=jobs[2], customer=jobs[2].customer, technician=technician.user, rating=1, comment="Hidden", is_visible=False)

    results = technician_client.get("/api/v1/technician/reviews/").json()["results"]

    assert [review["comment"] for review in results] == ["Neat work"]
    assert results[0]["customer_name"] == "Ananya"
    assert results[0]["service_name"] == "AC General Service"


def test_technician_can_request_and_list_leave(technician_client, technician):
    start = timezone.now() + timedelta(days=2)
    payload = {"start_at": start.isoformat(), "end_at": (start + timedelta(days=1)).isoformat(), "reason": "Family function"}

    created = technician_client.post("/api/v1/technician/leaves/", payload, format="json")
    listed = technician_client.get("/api/v1/technician/leaves/").json()["results"]

    assert created.status_code == 201
    assert created.json()["status"] == "PENDING"
    assert [leave["id"] for leave in listed] == [created.json()["id"]]
    assert TechnicianLeave.objects.get().technician == technician


def test_leave_request_rejects_overlap_and_past_dates(technician_client):
    start = timezone.now() + timedelta(days=2)
    payload = {"start_at": start.isoformat(), "end_at": (start + timedelta(days=1)).isoformat(), "reason": "Trip"}
    technician_client.post("/api/v1/technician/leaves/", payload, format="json")

    overlap = technician_client.post("/api/v1/technician/leaves/", payload, format="json")
    past = technician_client.post(
        "/api/v1/technician/leaves/",
        {"start_at": (timezone.now() - timedelta(days=3)).isoformat(), "end_at": (timezone.now() - timedelta(days=2)).isoformat(), "reason": "Old"},
        format="json",
    )

    assert overlap.status_code == 400
    assert past.status_code == 400


def test_performance_summarises_my_jobs_and_ratings(technician_client, technician, jobs):
    Review.objects.create(booking=jobs[0], customer=jobs[0].customer, technician=technician.user, rating=4, comment="Good")

    report = technician_client.get("/api/v1/technician/performance/").json()

    assert (report["total"], report["completed"], report["cancelled"], report["open"]) == (4, 2, 1, 1)
    assert report["completion_rate"] == 50
    assert Decimal(report["gross_revenue"]) == Decimal("2998.00")
    assert report["average_rating"] == 4.0
    assert report["penalties"] is None
    assert len(report["trend"]) == 3
    assert report["trend"][-1]["jobs"] == 2


def test_performance_rejects_bad_period(technician_client):
    assert technician_client.get("/api/v1/technician/performance/?period=last-week").status_code == 400


def test_technician_collects_balance_then_completes_job(technician_client, jobs):
    job = jobs[3]
    job.booking_status = BookingStatus.IN_PROGRESS
    job.save(update_fields=["booking_status"])

    blocked = technician_client.post(f"/api/v1/technician/jobs/{job.id}/complete/", {}, format="json")
    collected = technician_client.post(f"/api/v1/technician/jobs/{job.id}/collect-balance/", {"amount": "1200.00", "method": "CASH"}, format="json")
    completed = technician_client.post(f"/api/v1/technician/jobs/{job.id}/complete/", {}, format="json")

    assert blocked.status_code == 400
    assert collected.status_code == 200
    assert collected.json()["payment_status"] == "PAID"
    assert completed.status_code == 200
    assert completed.json()["booking_status"] == "COMPLETED"


def test_collect_balance_rejects_overpayment_and_other_technicians_jobs(technician_client, jobs):
    job = jobs[3]
    job.booking_status = BookingStatus.IN_PROGRESS
    job.save(update_fields=["booking_status"])
    other = technician_factory(phone_number="+919876543304", code="TECH-OTHER2")
    other_client = APIClient()
    other_client.force_authenticate(user=other.user)

    too_much = technician_client.post(f"/api/v1/technician/jobs/{job.id}/collect-balance/", {"amount": "5000.00", "method": "UPI"}, format="json")
    not_mine = other_client.post(f"/api/v1/technician/jobs/{job.id}/collect-balance/", {"amount": "100.00", "method": "UPI"}, format="json")

    assert too_much.status_code == 400
    assert not_mine.status_code == 404
