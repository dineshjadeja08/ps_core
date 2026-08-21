import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.locations.models import Address, ServiceArea


@pytest.fixture
def customer():
    return User.objects.create_user(
        phone_number="+919876543210",
        role=UserRole.CUSTOMER,
        is_verified=True,
    )


@pytest.fixture
def other_customer():
    return User.objects.create_user(
        phone_number="+919876543211",
        role=UserRole.CUSTOMER,
        is_verified=True,
    )


@pytest.fixture
def authenticated_client(customer):
    client = APIClient()
    client.force_authenticate(user=customer)
    return client


@pytest.fixture
def service_area():
    return ServiceArea.objects.create(
        name="Tirupattur Central",
        city="Tirupattur",
        state="Tamil Nadu",
        country="India",
        postal_code="635601",
    )


def address_payload(**overrides):
    payload = {
        "label": "Home",
        "recipient_name": "Dinesh",
        "phone": "+919876543210",
        "address_line_1": "12 Main Road",
        "address_line_2": "",
        "landmark": "Near bus stand",
        "locality": "Central",
        "city": "Tirupattur",
        "state": "Tamil Nadu",
        "postal_code": "635 601",
        "country": "India",
        "latitude": "12.490000",
        "longitude": "78.570000",
        "is_default": True,
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_create_address(authenticated_client):
    response = authenticated_client.post("/api/v1/addresses/", address_payload(), format="json")

    assert response.status_code == 201
    assert response.json()["postal_code"] == "635601"
    assert Address.objects.count() == 1


@pytest.mark.django_db
def test_list_own_addresses(authenticated_client, customer):
    Address.objects.create(customer=customer, **address_payload(postal_code="635601"))
    Address.objects.create(customer=customer, **address_payload(label="Office", postal_code="635602"))

    response = authenticated_client.get("/api/v1/addresses/")

    assert response.status_code == 200
    assert response.json()["count"] == 2


@pytest.mark.django_db
def test_cannot_access_another_customer_address(authenticated_client, other_customer):
    address = Address.objects.create(customer=other_customer, **address_payload(postal_code="635601"))

    response = authenticated_client.get(f"/api/v1/addresses/{address.id}/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_default_switching(authenticated_client, customer):
    first = Address.objects.create(customer=customer, **address_payload(postal_code="635601", is_default=True))
    second_payload = address_payload(label="Office", postal_code="635602", is_default=True)

    response = authenticated_client.post("/api/v1/addresses/", second_payload, format="json")

    assert response.status_code == 201
    first.refresh_from_db()
    assert first.is_default is False
    assert Address.objects.get(id=response.json()["id"]).is_default is True


@pytest.mark.django_db
def test_supported_postal_code(client, service_area):
    response = client.get("/api/v1/service-areas/check/?postal_code=635 601")

    assert response.status_code == 200
    assert response.json()["is_supported"] is True
    assert response.json()["service_area"]["postal_code"] == service_area.postal_code


@pytest.mark.django_db
def test_unsupported_postal_code(client):
    response = client.get("/api/v1/service-areas/check/?postal_code=000000")

    assert response.status_code == 200
    assert response.json() == {
        "postal_code": "000000",
        "is_supported": False,
        "service_area": None,
    }


@pytest.mark.django_db
def test_delete_deactivates_address(authenticated_client, customer):
    address = Address.objects.create(customer=customer, **address_payload(postal_code="635601", is_default=True))

    response = authenticated_client.delete(f"/api/v1/addresses/{address.id}/")

    assert response.status_code == 204
    address.refresh_from_db()
    assert address.is_active is False
    assert address.is_default is False


@pytest.mark.django_db
def test_coordinate_validation(authenticated_client):
    response = authenticated_client.post(
        "/api/v1/addresses/",
        address_payload(latitude="91.000000"),
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
