from unittest.mock import Mock

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.locations.providers import LocationProviderError, OlaMapsLocationProvider


@pytest.fixture
def authenticated_client():
    user = User.objects.create_user(
        phone_number="+919876543299",
        role=UserRole.CUSTOMER,
        is_verified=True,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_location_lookup_requires_authentication(client):
    response = client.get("/api/v1/location/reverse-geocode/?lat=13.0827&lng=80.2707")

    assert response.status_code == 401


@pytest.mark.django_db
def test_reverse_geocode_endpoint_returns_normalized_address(authenticated_client, monkeypatch):
    monkeypatch.setattr(
        "apps.locations.views.reverse_geocode",
        lambda latitude, longitude: {
            "formatted_address": "12 Mount Road, Chennai 600002",
            "house_number": "12",
            "street": "Mount Road",
            "locality": "Anna Salai",
            "city": "Chennai",
            "state": "Tamil Nadu",
            "pincode": "600002",
            "country": "India",
            "latitude": latitude,
            "longitude": longitude,
        },
    )

    response = authenticated_client.get("/api/v1/location/reverse-geocode/?lat=13.0827&lng=80.2707")

    assert response.status_code == 200
    assert response.json()["city"] == "Chennai"
    assert response.json()["pincode"] == "600002"


@pytest.mark.django_db
def test_autocomplete_validates_query_and_returns_suggestions(authenticated_client, monkeypatch):
    invalid = authenticated_client.get("/api/v1/location/autocomplete/?input=a")
    assert invalid.status_code == 400

    monkeypatch.setattr(
        "apps.locations.views.autocomplete",
        lambda query: [
            {
                "id": "ola-platform:123",
                "description": "Anna Nagar, Chennai",
                "main_text": "Anna Nagar",
                "secondary_text": "Chennai, Tamil Nadu",
                "formatted_address": "Anna Nagar, Chennai, Tamil Nadu",
                "house_number": "",
                "street": "Anna Nagar",
                "locality": "Anna Nagar",
                "city": "Chennai",
                "state": "Tamil Nadu",
                "pincode": "600040",
                "country": "India",
                "latitude": 13.085,
                "longitude": 80.21,
            }
        ],
    )

    response = authenticated_client.get("/api/v1/location/autocomplete/?input=Anna%20Nagar")

    assert response.status_code == 200
    assert response.json()["suggestions"][0]["main_text"] == "Anna Nagar"


@pytest.mark.django_db
def test_provider_failure_returns_service_unavailable(authenticated_client, monkeypatch):
    def fail(*args, **kwargs):
        raise LocationProviderError("Address lookup is temporarily unavailable.")

    monkeypatch.setattr("apps.locations.views.reverse_geocode", fail)

    response = authenticated_client.get("/api/v1/location/reverse-geocode/?lat=13.0827&lng=80.2707")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "API_ERROR"


@override_settings(OLA_MAPS_API_KEY="test-key", LOCATION_PROVIDER_TIMEOUT_SECONDS=3)
def test_ola_provider_normalizes_reverse_geocode(monkeypatch):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "geocodingResults": [
            {
                "formatted_address": "12 Mount Road, Anna Salai, Chennai, Tamil Nadu 600002, India",
                "geometry": {"location": {"lat": 13.0827, "lng": 80.2707}},
                "address_components": [
                    {"long_name": "12", "types": ["street_number"]},
                    {"long_name": "Mount Road", "types": ["street_address"]},
                    {"long_name": "Anna Salai", "types": ["sublocality_level_1"]},
                    {"long_name": "Chennai", "types": ["locality"]},
                    {"long_name": "Tamil Nadu", "types": ["administrative_area_level_1"]},
                    {"long_name": "600002", "types": ["postal_code"]},
                    {"long_name": "India", "types": ["country"]},
                ],
            }
        ],
        "status": "ok",
    }
    get = Mock(return_value=response)
    monkeypatch.setattr("apps.locations.providers.requests.get", get)

    result = OlaMapsLocationProvider().get_reverse_geocode(13.0827, 80.2707)

    assert result["house_number"] == "12"
    assert result["street"] == "Mount Road"
    assert result["city"] == "Chennai"
    assert result["pincode"] == "600002"
    assert get.call_args.kwargs["params"]["api_key"] == "test-key"
