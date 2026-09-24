from unittest.mock import Mock

import pytest
import requests
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from apps.locations.models import ServiceArea
from apps.locations.providers import LocationProviderError, OlaMapsLocationProvider, autocomplete, reverse_geocode
from common.throttles import LocationIPThrottle


def normalized_address(latitude=13.0827, longitude=80.2707):
    return {
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
        "supported_city": True,
        "serviceable": True,
    }


def ola_response(status_code, payload=None, text=None):
    response = Mock()
    response.status_code = status_code
    response.text = text if text is not None else "{}"
    response.json.return_value = payload if payload is not None else {}
    return response


@pytest.mark.django_db
def test_location_lookup_is_available_to_guests(client, monkeypatch):
    monkeypatch.setattr(
        "apps.locations.views.reverse_geocode",
        lambda latitude, longitude, **kwargs: normalized_address(latitude, longitude),
    )
    monkeypatch.setattr(
        "apps.locations.views.autocomplete",
        lambda query, **kwargs: [{"id": "ola:1", "description": "Avadi, Chennai", "main_text": "Avadi", "secondary_text": "Chennai", **normalized_address()}],
    )

    reverse_response = client.get("/api/v1/location/reverse-geocode/?lat=13.0827&lng=80.2707")
    autocomplete_response = client.get("/api/v1/location/autocomplete/?input=avadi")

    assert reverse_response.status_code == 200
    assert autocomplete_response.status_code == 200


@pytest.mark.django_db
def test_public_service_areas_can_be_filtered_by_city(client):
    ServiceArea.objects.create(name="Anna Nagar", city="Chennai", state="Tamil Nadu", postal_code="600040")
    ServiceArea.objects.create(name="Peelamedu", city="Coimbatore", state="Tamil Nadu", postal_code="641004")

    response = client.get("/api/v1/service-areas/?city=Chennai")

    assert response.status_code == 200
    assert [area["name"] for area in response.json()] == ["Anna Nagar"]


@pytest.mark.django_db
def test_location_inputs_are_validated_for_guests(client):
    assert client.get("/api/v1/location/autocomplete/?input=a").status_code == 400
    assert client.get("/api/v1/location/autocomplete/?input=avadi&lat=13.1").status_code == 400
    assert client.get("/api/v1/location/reverse-geocode/?lat=91&lng=80").status_code == 400
    assert client.get("/api/v1/location/reverse-geocode/?lat=13&lng=181").status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("reason", "expected_code"),
    [("misconfigured", "LOCATION_PROVIDER_MISCONFIGURED"), ("unavailable", "LOCATION_PROVIDER_UNAVAILABLE")],
)
def test_provider_failures_have_stable_safe_codes(client, monkeypatch, reason, expected_code):
    def fail(*args, **kwargs):
        raise LocationProviderError("internal provider detail", reason=reason)

    monkeypatch.setattr("apps.locations.views.reverse_geocode", fail)
    response = client.get("/api/v1/location/reverse-geocode/?lat=13.0827&lng=80.2707")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == expected_code
    assert "internal provider detail" not in response.json()["error"]["message"]


@pytest.mark.django_db
def test_location_throttle_is_per_ip(client, monkeypatch):
    cache.clear()
    monkeypatch.setattr(LocationIPThrottle, "get_rate", lambda self: "1/min")
    monkeypatch.setattr(
        "apps.locations.views.reverse_geocode",
        lambda latitude, longitude, **kwargs: normalized_address(latitude, longitude),
    )

    first = client.get("/api/v1/location/reverse-geocode/?lat=13.0827&lng=80.2707", REMOTE_ADDR="203.0.113.10")
    second = client.get("/api/v1/location/reverse-geocode/?lat=13.0828&lng=80.2708", REMOTE_ADDR="203.0.113.10")

    assert first.status_code == 200
    assert second.status_code == 429


@pytest.mark.django_db
@override_settings(OLA_MAPS_API_KEY="test-api-key", LOCATION_PROVIDER_TIMEOUT_SECONDS=3)
def test_ola_provider_uses_documented_contract_and_normalizes(monkeypatch):
    ServiceArea.objects.create(name="Chennai Central", city="Chennai", state="Tamil Nadu", postal_code="600002")
    response = ola_response(
        200,
        {
            "results": [
                {
                    "formatted_address": "12 Mount Road, Anna Salai, Chennai, Tamil Nadu 600002, India",
                    "geometry": {"location": {"lat": 13.0827, "lng": 80.2707}},
                    "address_components": [
                        {"long_name": "12", "types": ["street_number"]},
                        {"long_name": "Mount Road", "types": ["route"]},
                        {"long_name": "Anna Salai", "types": ["sublocality_level_1"]},
                        {"long_name": "Chennai", "types": ["locality"]},
                        {"long_name": "Tamil Nadu", "types": ["administrative_area_level_1"]},
                        {"long_name": "600002", "types": ["postal_code"]},
                        {"long_name": "India", "types": ["country"]},
                    ],
                }
            ],
            "status": "ok",
        },
    )
    get = Mock(return_value=response)
    monkeypatch.setattr("apps.locations.providers.requests.get", get)

    result = OlaMapsLocationProvider().get_reverse_geocode(13.0827, 80.2707, request_id="request-123")

    assert result["city"] == "Chennai"
    assert result["pincode"] == "600002"
    assert result["supported_city"] is True
    assert result["serviceable"] is True
    assert get.call_args.kwargs["params"]["latlng"] == "13.0827,80.2707"
    assert get.call_args.kwargs["params"]["api_key"] == "test-api-key"
    assert get.call_args.kwargs["headers"]["X-Request-Id"] == "request-123"


@pytest.mark.django_db
@override_settings(OLA_MAPS_API_KEY="test-api-key")
def test_autocomplete_uses_location_bias_and_parses_missing_components(monkeypatch):
    ServiceArea.objects.create(name="Anna Nagar", city="Chennai", state="Tamil Nadu", postal_code="600040")
    get = Mock(return_value=ola_response(200, {
        "predictions": [{
            "place_id": "ola-platform:123",
            "description": "Anna Nagar, Chennai, Tamil Nadu 600040, India",
            "structured_formatting": {"main_text": "Anna Nagar", "secondary_text": "Chennai, Tamil Nadu"},
            "geometry": {"location": {"lat": 13.085, "lng": 80.21}},
        }],
        "status": "ok",
    }))
    monkeypatch.setattr("apps.locations.providers.requests.get", get)

    result = OlaMapsLocationProvider().get_autocomplete("Anna", latitude=13.08, longitude=80.27)

    assert get.call_args.kwargs["params"]["location"] == "13.08,80.27"
    assert result[0]["city"] == "Chennai"
    assert result[0]["pincode"] == "600040"
    assert result[0]["serviceable"] is True


@pytest.mark.django_db
@override_settings(OLA_MAPS_API_KEY="test-api-key")
@pytest.mark.parametrize("status_code", [401, 403])
def test_ola_auth_failures_are_misconfigured_without_retry(monkeypatch, status_code):
    get = Mock(return_value=ola_response(status_code, text='{"message":"invalid api_key=test-api-key"}'))
    monkeypatch.setattr("apps.locations.providers.requests.get", get)

    with pytest.raises(LocationProviderError) as caught:
        OlaMapsLocationProvider().get_autocomplete("avadi")

    assert caught.value.reason == "misconfigured"
    assert "test-api-key" not in caught.value.response_snippet
    assert get.call_count == 1


@pytest.mark.django_db
@override_settings(OLA_MAPS_API_KEY="test-api-key")
def test_ola_429_is_unavailable_without_retry(monkeypatch):
    get = Mock(return_value=ola_response(429, text='{"message":"rate limit"}'))
    monkeypatch.setattr("apps.locations.providers.requests.get", get)

    with pytest.raises(LocationProviderError) as caught:
        OlaMapsLocationProvider().get_autocomplete("avadi")

    assert caught.value.reason == "unavailable"
    assert get.call_count == 1


@pytest.mark.django_db
@override_settings(OLA_MAPS_API_KEY="test-api-key")
def test_ola_5xx_retries_once(monkeypatch):
    get = Mock(side_effect=[ola_response(503, text='{"message":"down"}'), ola_response(200, {"predictions": [], "status": "zero_results"})])
    monkeypatch.setattr("apps.locations.providers.requests.get", get)

    assert OlaMapsLocationProvider().get_autocomplete("avadi") == []
    assert get.call_count == 2


@pytest.mark.django_db
@override_settings(OLA_MAPS_API_KEY="test-api-key")
def test_ola_timeout_retries_once(monkeypatch):
    get = Mock(side_effect=requests.Timeout("secret URL must not be logged"))
    monkeypatch.setattr("apps.locations.providers.requests.get", get)

    with pytest.raises(LocationProviderError) as caught:
        OlaMapsLocationProvider().get_autocomplete("avadi")

    assert caught.value.status_code == "timeout"
    assert get.call_count == 2


@pytest.mark.django_db
@override_settings(OLA_MAPS_API_KEY="test-api-key")
def test_malformed_ola_body_is_unavailable(monkeypatch):
    get = Mock(return_value=ola_response(200, {"status": "ok"}, text='{"status":"ok"}'))
    monkeypatch.setattr("apps.locations.providers.requests.get", get)

    with pytest.raises(LocationProviderError) as caught:
        OlaMapsLocationProvider().get_autocomplete("avadi")

    assert caught.value.reason == "unavailable"


@pytest.mark.django_db
@override_settings(
    LOCATION_PROVIDER="tests.test_location_lookup.CachedProvider",
    LOCATION_AUTOCOMPLETE_CACHE_SECONDS=300,
    LOCATION_REVERSE_CACHE_SECONDS=3600,
)
def test_identical_queries_are_cached(monkeypatch):
    cache.clear()
    CachedProvider.autocomplete_calls = 0
    CachedProvider.reverse_calls = 0

    autocomplete("avadi", city="Chennai")
    autocomplete("  AVADI  ", city="chennai")
    reverse_geocode(13.082712, 80.270712)
    reverse_geocode(13.082714, 80.270714)

    assert CachedProvider.autocomplete_calls == 1
    assert CachedProvider.reverse_calls == 1


class CachedProvider:
    autocomplete_calls = 0
    reverse_calls = 0

    def get_autocomplete(self, query, **kwargs):
        self.__class__.autocomplete_calls += 1
        return []

    def get_reverse_geocode(self, latitude, longitude, **kwargs):
        self.__class__.reverse_calls += 1
        return normalized_address(latitude, longitude)
