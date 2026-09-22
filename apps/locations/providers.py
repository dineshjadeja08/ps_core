import hashlib
import logging
from datetime import timedelta
from typing import Protocol
from uuid import uuid4

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.module_loading import import_string


logger = logging.getLogger(__name__)


class LocationProviderError(Exception):
    """Raised when a configured geocoding provider cannot fulfil a lookup."""


class LocationProvider(Protocol):
    def get_reverse_geocode(self, latitude: float, longitude: float) -> dict: ...

    def get_autocomplete(self, query: str) -> list[dict]: ...


class OlaMapsLocationProvider:
    REVERSE_GEOCODE_URL = "https://api.olamaps.io/places/v1/reverse-geocode"
    AUTOCOMPLETE_URL = "https://api.olamaps.io/places/v1/autocomplete"

    def __init__(self):
        self.api_key = settings.OLA_MAPS_API_KEY
        self.timeout = settings.LOCATION_PROVIDER_TIMEOUT_SECONDS

    def get_reverse_geocode(self, latitude: float, longitude: float) -> dict:
        payload = self._get(
            self.REVERSE_GEOCODE_URL,
            {"latlng": f"{latitude},{longitude}", "language": "en"},
        )
        results = payload.get("geocodingResults") or payload.get("results") or []
        if not results:
            raise LocationProviderError("No address was found for this location.")
        return _normalise_place(results[0], fallback_latitude=latitude, fallback_longitude=longitude)

    def get_autocomplete(self, query: str) -> list[dict]:
        payload = self._get(self.AUTOCOMPLETE_URL, {"input": query, "language": "en"})
        predictions = payload.get("predictions") or payload.get("results") or []
        return [_normalise_suggestion(item) for item in predictions[:8]]

    def _get(self, url: str, params: dict) -> dict:
        if not self.api_key:
            raise LocationProviderError("Address lookup is not configured.")
        _track_provider_call()
        try:
            response = requests.get(
                url,
                params={**params, "api_key": self.api_key},
                headers={"Accept": "application/json", "X-Request-Id": str(uuid4())},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Ola Maps location lookup failed: %s", exc.__class__.__name__)
            raise LocationProviderError("Address lookup is temporarily unavailable.") from exc

        if not isinstance(payload, dict):
            raise LocationProviderError("The address provider returned an invalid response.")
        return payload


def get_location_provider() -> LocationProvider:
    provider_class = import_string(settings.LOCATION_PROVIDER)
    return provider_class()


def reverse_geocode(latitude: float, longitude: float) -> dict:
    cache_key = f"location:reverse:{latitude:.5f}:{longitude:.5f}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    result = get_location_provider().get_reverse_geocode(latitude, longitude)
    cache.set(cache_key, result, timeout=settings.LOCATION_REVERSE_CACHE_SECONDS)
    return result


def autocomplete(query: str) -> list[dict]:
    normalized_query = " ".join(query.lower().split())
    digest = hashlib.sha256(normalized_query.encode("utf-8")).hexdigest()[:24]
    cache_key = f"location:autocomplete:{digest}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    result = get_location_provider().get_autocomplete(query)
    cache.set(cache_key, result, timeout=settings.LOCATION_AUTOCOMPLETE_CACHE_SECONDS)
    return result


def _normalise_place(place: dict, *, fallback_latitude=None, fallback_longitude=None) -> dict:
    components = place.get("address_components") or []

    def component(*types):
        for item in components:
            item_types = item.get("types") or []
            if any(item_type in item_types for item_type in types):
                return item.get("long_name") or item.get("short_name") or ""
        return ""

    geometry = place.get("geometry") or {}
    location = geometry.get("location") or geometry
    house_number = component("street_number", "premise", "subpremise")
    street = component("street_address", "route") or place.get("name") or ""
    locality = component("sublocality_level_1", "sublocality", "neighborhood")
    city = component("locality", "administrative_area_level_2", "administrative_area_level_3")

    return {
        "formatted_address": place.get("formatted_address") or place.get("description") or "",
        "house_number": house_number,
        "street": street,
        "locality": locality,
        "city": city,
        "state": component("administrative_area_level_1"),
        "pincode": component("postal_code"),
        "country": component("country") or "India",
        "latitude": location.get("lat", fallback_latitude),
        "longitude": location.get("lng", fallback_longitude),
    }


def _normalise_suggestion(place: dict) -> dict:
    structured = place.get("structured_formatting") or {}
    normalized = _normalise_place(place)
    description = place.get("description") or normalized["formatted_address"] or structured.get("main_text") or ""
    return {
        "id": place.get("place_id") or place.get("reference") or description,
        "description": description,
        "main_text": structured.get("main_text") or place.get("name") or description,
        "secondary_text": structured.get("secondary_text") or "",
        **normalized,
    }


def _track_provider_call():
    month = timezone.now().strftime("%Y-%m")
    key = f"location:provider-calls:{month}"
    cache.add(key, 0, timeout=int(timedelta(days=40).total_seconds()))
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=int(timedelta(days=40).total_seconds()))
        count = 1
    if count in {1, 50_000, 80_000, 90_000, 100_000}:
        log = logger.warning if count >= 80_000 else logger.info
        log("Ola Maps monthly call count is %s for %s.", count, month)
