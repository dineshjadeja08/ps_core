import hashlib
import json
import logging
import re
import time
from datetime import timedelta
from typing import Protocol
from uuid import uuid4

import requests
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone
from django.utils.module_loading import import_string

from apps.locations.models import ServiceArea


logger = logging.getLogger(__name__)
SUPPORTED_CITIES = {"chennai", "coimbatore"}
PINCODE_PATTERN = re.compile(r"(?<!\d)([1-9]\d{5})(?!\d)")


class LocationProviderError(Exception):
    """A safe, classified failure returned by a geocoding provider."""

    def __init__(
        self,
        message="Address lookup is temporarily unavailable.",
        *,
        reason="unavailable",
        status_code=None,
        response_snippet="",
        latency_ms=None,
        request_id="",
    ):
        super().__init__(message)
        self.reason = reason
        self.status_code = status_code
        self.response_snippet = response_snippet
        self.latency_ms = latency_ms
        self.request_id = request_id


class LocationProvider(Protocol):
    def get_reverse_geocode(self, latitude: float, longitude: float, *, request_id: str = "") -> dict: ...

    def get_autocomplete(
        self,
        query: str,
        *,
        latitude: float | None = None,
        longitude: float | None = None,
        city: str = "",
        request_id: str = "",
    ) -> list[dict]: ...


class OlaMapsLocationProvider:
    BASE_URL = "https://api.olamaps.io"
    REVERSE_GEOCODE_PATH = "/places/v1/reverse-geocode"
    AUTOCOMPLETE_PATH = "/places/v1/autocomplete"

    def __init__(self):
        self.api_key = str(settings.OLA_MAPS_API_KEY or "").strip()
        self.timeout = min(max(int(settings.LOCATION_PROVIDER_TIMEOUT_SECONDS), 1), 15)

    def get_reverse_geocode(self, latitude: float, longitude: float, *, request_id: str = "") -> dict:
        payload = self._get(
            self.REVERSE_GEOCODE_PATH,
            {"latlng": f"{latitude},{longitude}", "language": "en"},
            request_id=request_id,
        )
        if "results" not in payload and "geocodingResults" not in payload:
            raise self._malformed_error(request_id)
        results = payload.get("results") or payload.get("geocodingResults") or []
        if not isinstance(results, list):
            raise self._malformed_error(request_id)
        if not results:
            raise LocationProviderError(request_id=request_id)
        try:
            return _normalise_place(results[0], fallback_latitude=latitude, fallback_longitude=longitude)
        except (AttributeError, TypeError, ValueError) as exc:
            raise self._malformed_error(request_id) from exc

    def get_autocomplete(
        self,
        query: str,
        *,
        latitude: float | None = None,
        longitude: float | None = None,
        city: str = "",
        request_id: str = "",
    ) -> list[dict]:
        params = {"input": query, "language": "en"}
        if latitude is not None and longitude is not None:
            params["location"] = f"{latitude},{longitude}"
        elif city and city.casefold() not in query.casefold():
            params["input"] = f"{query}, {city}"

        payload = self._get(self.AUTOCOMPLETE_PATH, params, request_id=request_id)
        if "predictions" not in payload and "results" not in payload:
            raise self._malformed_error(request_id)
        predictions = payload.get("predictions") or payload.get("results") or []
        if not isinstance(predictions, list):
            raise self._malformed_error(request_id)
        try:
            return [_normalise_suggestion(item) for item in predictions[:8] if isinstance(item, dict)]
        except (AttributeError, TypeError, ValueError) as exc:
            raise self._malformed_error(request_id) from exc

    def _get(self, path: str, params: dict, *, request_id: str = "") -> dict:
        provider_request_id = _safe_request_id(request_id)
        if not self.api_key:
            error = LocationProviderError(
                "Address lookup is not configured.",
                reason="misconfigured",
                request_id=provider_request_id,
            )
            self._log_failure(path, error)
            raise error

        _track_provider_call()
        for attempt in range(2):
            started = time.monotonic()
            try:
                response = requests.get(
                    f"{self.BASE_URL}{path}",
                    params={**params, "api_key": self.api_key},
                    headers={"Accept": "application/json", "X-Request-Id": provider_request_id},
                    timeout=self.timeout,
                )
            except requests.Timeout as exc:
                error = LocationProviderError(
                    status_code="timeout",
                    latency_ms=_elapsed_ms(started),
                    request_id=provider_request_id,
                )
                self._log_failure(path, error, attempt=attempt + 1)
                if attempt == 0:
                    continue
                raise error from exc
            except requests.RequestException as exc:
                error = LocationProviderError(
                    status_code="network_error",
                    latency_ms=_elapsed_ms(started),
                    request_id=provider_request_id,
                )
                self._log_failure(path, error, attempt=attempt + 1)
                raise error from exc

            latency_ms = _elapsed_ms(started)
            status_code = response.status_code
            snippet = _safe_body_snippet(response.text)
            if status_code in {401, 403}:
                error = LocationProviderError(
                    "Address lookup is not configured.",
                    reason="misconfigured",
                    status_code=status_code,
                    response_snippet=snippet,
                    latency_ms=latency_ms,
                    request_id=provider_request_id,
                )
                self._log_failure(path, error, attempt=attempt + 1)
                raise error
            if status_code == 429 or status_code >= 500:
                error = LocationProviderError(
                    status_code=status_code,
                    response_snippet=snippet,
                    latency_ms=latency_ms,
                    request_id=provider_request_id,
                )
                self._log_failure(path, error, attempt=attempt + 1)
                if status_code >= 500 and attempt == 0:
                    continue
                raise error
            if status_code >= 400:
                error = LocationProviderError(
                    status_code=status_code,
                    response_snippet=snippet,
                    latency_ms=latency_ms,
                    request_id=provider_request_id,
                )
                self._log_failure(path, error, attempt=attempt + 1)
                raise error

            try:
                payload = response.json()
            except ValueError as exc:
                error = self._malformed_error(provider_request_id, status_code=status_code, latency_ms=latency_ms, snippet=snippet)
                self._log_failure(path, error, attempt=attempt + 1)
                raise error from exc
            if not isinstance(payload, dict):
                error = self._malformed_error(provider_request_id, status_code=status_code, latency_ms=latency_ms, snippet=snippet)
                self._log_failure(path, error, attempt=attempt + 1)
                raise error
            return payload

        raise LocationProviderError(request_id=provider_request_id)

    @staticmethod
    def _malformed_error(request_id, *, status_code=200, latency_ms=None, snippet=""):
        return LocationProviderError(
            status_code=status_code,
            response_snippet=snippet,
            latency_ms=latency_ms,
            request_id=request_id,
        )

    @staticmethod
    def _log_failure(path, error, *, attempt=1):
        logger.warning(
            "ola_maps_failure endpoint=%s request_id=%s status=%s latency_ms=%s attempt=%s body=%s",
            path,
            error.request_id,
            error.status_code or "misconfigured",
            error.latency_ms if error.latency_ms is not None else "n/a",
            attempt,
            error.response_snippet or "<empty>",
        )


def get_location_provider(provider_path=None) -> LocationProvider:
    provider_class = import_string(provider_path or settings.LOCATION_PROVIDER)
    return provider_class()


def reverse_geocode(latitude: float, longitude: float, *, request_id: str = "") -> dict:
    cache_key = f"location:reverse:{latitude:.4f}:{longitude:.4f}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    result = _call_with_optional_fallback(
        "get_reverse_geocode",
        latitude,
        longitude,
        request_id=request_id,
    )
    cache.set(cache_key, result, timeout=settings.LOCATION_REVERSE_CACHE_SECONDS)
    return result


def autocomplete(
    query: str,
    *,
    latitude: float | None = None,
    longitude: float | None = None,
    city: str = "",
    request_id: str = "",
) -> list[dict]:
    normalized_query = " ".join(query.casefold().split())
    bias = f"{latitude:.4f}:{longitude:.4f}" if latitude is not None and longitude is not None else city.casefold().strip()
    digest = hashlib.sha256(f"{normalized_query}|{bias}".encode("utf-8")).hexdigest()[:24]
    cache_key = f"location:autocomplete:{digest}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    result = _call_with_optional_fallback(
        "get_autocomplete",
        query,
        latitude=latitude,
        longitude=longitude,
        city=city,
        request_id=request_id,
    )
    cache.set(cache_key, result, timeout=settings.LOCATION_AUTOCOMPLETE_CACHE_SECONDS)
    return result


def _call_with_optional_fallback(method_name, *args, **kwargs):
    try:
        return getattr(get_location_provider(), method_name)(*args, **kwargs)
    except LocationProviderError:
        fallback_path = getattr(settings, "LOCATION_FALLBACK_PROVIDER", "")
        if not fallback_path:
            raise
        logger.warning("location_provider_fallback provider=%s", fallback_path)
        return getattr(get_location_provider(fallback_path), method_name)(*args, **kwargs)


def _normalise_place(place: dict, *, fallback_latitude=None, fallback_longitude=None) -> dict:
    components = place.get("address_components") or []
    if not isinstance(components, list):
        components = []

    def component(*types):
        for item in components:
            if not isinstance(item, dict):
                continue
            item_types = item.get("types") or []
            if any(item_type in item_types for item_type in types):
                return str(item.get("long_name") or item.get("short_name") or "")
        return ""

    geometry = place.get("geometry") or {}
    location = geometry.get("location") or geometry if isinstance(geometry, dict) else {}
    if not isinstance(location, dict):
        location = {}
    formatted_address = str(place.get("formatted_address") or place.get("description") or "")
    house_number = component("street_number", "premise", "subpremise")
    street = component("street_address", "route") or str(place.get("name") or "")
    locality = component("sublocality_level_1", "sublocality", "neighborhood")
    component_city = component("locality", "administrative_area_level_2", "administrative_area_level_3")
    city = _city_from_text(formatted_address) or component_city
    pincode = component("postal_code") or _pincode_from_text(formatted_address)
    state = component("administrative_area_level_1") or ("Tamil Nadu" if city.casefold() in SUPPORTED_CITIES else "")
    result = {
        "formatted_address": formatted_address,
        "house_number": house_number,
        "street": street,
        "locality": locality,
        "city": city,
        "state": state,
        "pincode": pincode,
        "country": component("country") or "India",
        "latitude": location.get("lat", fallback_latitude),
        "longitude": location.get("lng", fallback_longitude),
    }
    result.update(_serviceability(city, pincode))
    return result


def _normalise_suggestion(place: dict) -> dict:
    structured = place.get("structured_formatting") or {}
    if not isinstance(structured, dict):
        structured = {}
    normalized = _normalise_place(place)
    description = str(place.get("description") or normalized["formatted_address"] or structured.get("main_text") or "")
    return {
        "id": str(place.get("place_id") or place.get("reference") or description),
        "description": description,
        "main_text": str(structured.get("main_text") or place.get("name") or description),
        "secondary_text": str(structured.get("secondary_text") or ""),
        **normalized,
    }


def _serviceability(city: str, pincode: str) -> dict:
    normalized_city = city.casefold().strip()
    supported_city = normalized_city in SUPPORTED_CITIES
    query = Q()
    if pincode:
        query |= Q(postal_code=pincode)
    if city:
        query |= Q(city__iexact=city)
    serviceable = bool(query) and ServiceArea.objects.filter(query, is_active=True).exists()
    return {"supported_city": supported_city, "serviceable": serviceable}


def _city_from_text(text: str) -> str:
    folded = text.casefold()
    for city in ("Chennai", "Coimbatore"):
        if city.casefold() in folded:
            return city
    return ""


def _pincode_from_text(text: str) -> str:
    match = PINCODE_PATTERN.search(text)
    return match.group(1) if match else ""


def _safe_request_id(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]", "", str(value or ""))[:64]
    return value or str(uuid4())


def _safe_body_snippet(body: str) -> str:
    raw = str(body or "")[:2000]
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        snippet = raw[:500]
    else:
        if isinstance(payload, dict):
            safe_payload = {
                key: payload[key]
                for key in ("status", "error_message", "message", "info_messages")
                if key in payload
            }
            snippet = json.dumps(safe_payload, ensure_ascii=True)[:500]
        else:
            snippet = "<non-object response>"
    snippet = re.sub(r"(?i)(api[_-]?key)([=\"':%20 ]+)[^&\"', }]+", r"\1\2<redacted>", snippet)
    snippet = re.sub(r'(?i)("(?:input|address|latlng)"\s*:\s*")[^"]*', r'\1<redacted>', snippet)
    snippet = re.sub(r"(?<!\d)[1-9]\d{5}(?!\d)", "<redacted-pincode>", snippet)
    snippet = re.sub(r"(?<!\d)-?\d{1,2}\.\d{3,},\s*-?\d{1,3}\.\d{3,}(?!\d)", "<redacted-coordinates>", snippet)
    return " ".join(snippet.split())


def _elapsed_ms(started):
    return round((time.monotonic() - started) * 1000)


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
