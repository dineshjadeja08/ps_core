from importlib import import_module
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.db import connection
from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalogue.models import Service, ServiceCategory
from apps.operations.models import FAQ


migration = import_module("apps.operations.migrations.0005_service_visiting_charge_faq")
pytestmark = pytest.mark.django_db


def create_services():
    category = ServiceCategory.objects.create(name="Test services", slug="visiting-charge-services")
    return [
        Service.objects.create(
            category=category,
            name=f"Service {index}",
            slug=f"visiting-charge-service-{index}",
            base_price=1000,
            advance_amount=299,
            estimated_duration_minutes=60,
        )
        for index in range(2)
    ]


def seed_faqs():
    migration.add_visiting_charge_faq(apps, SimpleNamespace(connection=connection))


def test_visiting_charge_faq_is_published_for_each_service_at_order_five():
    services = create_services()
    earlier = FAQ.objects.create(service=services[0], question="Earlier", answer="Kept", display_order=4)
    later = FAQ.objects.create(service=services[0], question="Existing fifth", answer="Kept", display_order=5)
    seed_faqs()

    client = APIClient()
    for service in services:
        faq = FAQ.objects.get(service=service, question=migration.QUESTION)
        assert faq.answer == migration.ANSWER
        assert faq.display_order == 5
        assert faq.is_active
        response = client.get(reverse("public-faq-list"), {"service_id": str(service.id)})
        assert response.status_code == 200
        assert any(item["question"] == migration.QUESTION and item["display_order"] == 5 for item in response.data)

    earlier.refresh_from_db()
    later.refresh_from_db()
    assert earlier.display_order == 4
    assert later.display_order == 6
    assert later.answer == "Kept"

    seed_faqs()
    later.refresh_from_db()
    assert later.display_order == 6
    assert FAQ.objects.filter(service__in=services, question=migration.QUESTION).count() == 2


def test_existing_visiting_charge_faq_is_updated_without_a_duplicate():
    service = create_services()[0]
    faq = FAQ.objects.create(
        service=service, question=migration.QUESTION, answer="Old answer", display_order=8, is_active=False
    )
    seed_faqs()
    faq.refresh_from_db()
    assert faq.answer == migration.ANSWER
    assert faq.display_order == 5
    assert faq.is_active
    assert FAQ.objects.filter(service=service, question=migration.QUESTION).count() == 1
