import hashlib
import json
import logging
import re
import time
from datetime import timedelta
from typing import Protocol
from uuid import uuid4
from urllib.parse import quote

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

    def get_geocode(self, place_id: str, *, request_id: str = "") -> dict: ...


class GoogleMapsLocationProvider:
    BASE_URL = "https://maps.googleapis.com/maps/api"
    REVERSE_GEOCODE_PATH = "/geocode/json"
    PLACES_BASE_URL = "https://places.googleapis.com/v1"
    AUTOCOMPLETE_PATH = "/places:autocomplete"
    PLACE_FIELDS = "id,formattedAddress,addressComponents,location"

    def __init__(self):
        self.api_key = str(settings.GOOGLE_MAPS_API_KEY or "").strip()
        self.timeout = min(max(int(settings.LOCATION_PROVIDER_TIMEOUT_SECONDS), 1), 15)

    def get_reverse_geocode(self, latitude: float, longitude: float, *, request_id: str = "") -> dict:
        payload = self._get(
            self.REVERSE_GEOCODE_PATH,
            {"latlng": f"{latitude},{longitude}", "language": "en"},
            request_id=request_id,
        )
        if "results" not in payload:
            raise self._malformed_error(request_id)
        results = payload.get("results") or []
        if not isinstance(results, list):
            raise self._malformed_error(request_id)
        if not results:
            raise LocationProviderError(request_id=request_id)
        try:
            return _normalise_results(results, fallback_latitude=latitude, fallback_longitude=longitude)
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
        params = {"input": query, "languageCode": "en", "includedRegionCodes": ["in"], "regionCode": "in"}
        if latitude is not None and longitude is not None:
            params["locationBias"] = {"circle": {"center": {"latitude": latitude, "longitude": longitude}, "radius": 50000.0}}
        elif city and city.casefold() not in query.casefold():
            params["input"] = f"{query}, {city}"

        payload = self._request(self.AUTOCOMPLETE_PATH, params, request_id=request_id, places=True, method="POST")
        # Protobuf JSON may omit the empty suggestions array when there are no matches.
        predictions = payload.get("suggestions", [])
        if not isinstance(predictions, list):
            raise self._malformed_error(request_id)
        try:
            suggestions = []
            for item in predictions[:8]:
                prediction = item.get("placePrediction") if isinstance(item, dict) else None
                if not isinstance(prediction, dict) or not prediction.get("placeId"):
                    raise self._malformed_error(request_id)
                structured = prediction.get("structuredFormat") or {}
                suggestions.append(_normalise_suggestion({
                    "place_id": prediction["placeId"],
                    "description": (prediction.get("text") or {}).get("text", ""),
                    "structured_formatting": {
                        "main_text": (structured.get("mainText") or {}).get("text", ""),
                        "secondary_text": (structured.get("secondaryText") or {}).get("text", ""),
                    },
                }))
            return suggestions
        except (AttributeError, TypeError, ValueError) as exc:
            raise self._malformed_error(request_id) from exc

    def get_geocode(self, place_id: str, *, request_id: str = "") -> dict:
        path = f"/places/{quote(place_id, safe='')}"
        payload = self._request(path, {"languageCode": "en", "regionCode": "in"}, request_id=request_id, places=True)
        try:
            location = payload["location"]
            latitude, longitude = float(location["latitude"]), float(location["longitude"])
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValueError("Invalid place coordinates")
            components = payload.get("addressComponents", [])
            if not isinstance(components, list):
                raise ValueError("Invalid address components")
            result = _normalise_place({
                "formatted_address": payload.get("formattedAddress", ""),
                "geometry": {"location": {"lat": latitude, "lng": longitude}},
                "address_components": [{
                    "long_name": item.get("longText", ""),
                    "short_name": item.get("shortText", ""),
                    "types": item.get("types", []),
                } for item in components],
            })
        except (KeyError, AttributeError, TypeError, ValueError) as exc:
            raise self._malformed_error(request_id) from exc
        if not all(result.get(field) for field in ("city", "state", "pincode")):
            fallback = self.get_reverse_geocode(round(latitude, 6), round(longitude, 6), request_id=request_id)
            for field in ("formatted_address", "house_number", "street", "locality", "city", "state", "pincode", "country"):
                if not result.get(field):
                    result[field] = fallback.get(field, "")
            result.update(_serviceability(result["city"], result["pincode"]))
        return result

    def _get(self, path: str, params: dict, *, request_id: str = "") -> dict:
        return self._request(path, params, request_id=request_id)

    def _request(self, path: str, params: dict, *, request_id: str = "", places=False, method="GET") -> dict:
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
                headers = {"Accept": "application/json", "X-Request-Id": provider_request_id}
                if places:
                    headers["X-Goog-Api-Key"] = self.api_key
                    if method == "GET":
                        headers["X-Goog-FieldMask"] = self.PLACE_FIELDS
                url = f"{self.PLACES_BASE_URL if places else self.BASE_URL}{path}"
                if method == "POST":
                    response = requests.post(url, json=params, headers=headers, timeout=self.timeout)
                else:
                    response = requests.get(url, params=params if places else {**params, "key": self.api_key}, headers=headers, timeout=self.timeout)
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
                    reason="not_found" if places and status_code == 404 else "unavailable",
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
            provider_status = str(payload.get("status", "OK"))
            if places and "error" in payload:
                error = LocationProviderError(status_code=status_code, response_snippet=snippet, latency_ms=latency_ms, request_id=provider_request_id)
                self._log_failure(path, error, attempt=attempt + 1)
                raise error
            if provider_status not in {"OK", "ZERO_RESULTS"}:
                reason = "misconfigured" if provider_status in {"REQUEST_DENIED", "INVALID_REQUEST"} else "unavailable"
                error = LocationProviderError(
                    "Address lookup is not configured." if reason == "misconfigured" else "Address lookup is temporarily unavailable.",
                    reason=reason,
                    status_code=provider_status,
                    response_snippet=_safe_body_snippet(response.text),
                    latency_ms=latency_ms,
                    request_id=provider_request_id,
                )
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
            "google_maps_failure endpoint=%s request_id=%s status=%s latency_ms=%s attempt=%s body=%s",
            path,
            error.request_id,
            error.status_code or "misconfigured",
            error.latency_ms if error.latency_ms is not None else "n/a",
            attempt,
            error.response_snippet or "<empty>",
        )


def get_location_provider(provider_path=None) -> LocationProvider:
    configured_path = provider_path or settings.LOCATION_PROVIDER
    # Cloud Run may retain the provider path from deployments made before the
    # Google Maps migration. Keep those revisions functional while the stale
    # environment override is removed.
    if configured_path == "apps.locations.providers.OlaMapsLocationProvider":
        configured_path = "apps.locations.providers.GoogleMapsLocationProvider"
    provider_class = import_string(configured_path)
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


def geocode_place(place_id: str, *, request_id: str = "") -> dict:
    cache_key = f"location:place:{hashlib.sha256(place_id.encode('utf-8')).hexdigest()[:24]}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    result = _call_with_optional_fallback("get_geocode", place_id, request_id=request_id)
    cache.set(cache_key, result, timeout=settings.LOCATION_REVERSE_CACHE_SECONDS)
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


def parse_components(address_components) -> dict:
    components = address_components or []
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

    premise = component("premise")
    street_number = component("street_number")
    route = component("route")
    return {
        "line1": ", ".join(part for part in (premise, street_number, route) if part),
        "area": component("sublocality_level_1", "sublocality", "neighborhood"),
        "city": component("locality") or component("administrative_area_level_3") or component("administrative_area_level_2"),
        "state": component("administrative_area_level_1"),
        "pincode": component("postal_code"),
    }


def _normalise_results(results: list[dict], *, fallback_latitude=None, fallback_longitude=None) -> dict:
    merged = _normalise_place(results[0], fallback_latitude=fallback_latitude, fallback_longitude=fallback_longitude)
    for place in results[1:]:
        candidate = _normalise_place(place, fallback_latitude=fallback_latitude, fallback_longitude=fallback_longitude)
        for field in ("house_number", "street", "locality", "city", "state", "pincode", "country", "latitude", "longitude"):
            if not merged.get(field) and candidate.get(field):
                merged[field] = candidate[field]
        if merged["city"] and merged["state"] and merged["pincode"]:
            break
    merged.update(_serviceability(merged["city"], merged["pincode"]))
    return merged


def _normalise_place(place: dict, *, fallback_latitude=None, fallback_longitude=None) -> dict:
    components = place.get("address_components") or []
    parsed = parse_components(components)

    def component(*types):
        for item in components if isinstance(components, list) else []:
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
    locality = parsed["area"]
    component_city = parsed["city"]
    city = _city_from_text(formatted_address) or component_city
    pincode = parsed["pincode"] or _pincode_from_text(formatted_address)
    state = parsed["state"] or ("Tamil Nadu" if city.casefold() in SUPPORTED_CITIES else "")
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
            if isinstance(payload.get("error"), dict):
                safe_payload["error"] = {
                    key: payload["error"][key]
                    for key in ("code", "status", "message")
                    if key in payload["error"]
                }
            snippet = json.dumps(safe_payload, ensure_ascii=True)[:500]
        else:
            snippet = "<non-object response>"
    snippet = re.sub(r"(?i)(api[_-]?key)([=\"':%20 ]+)[^&\"', }]+", r"\1\2<redacted>", snippet)
    snippet = re.sub(r"AIza[A-Za-z0-9_-]+", "<redacted-key>", snippet)
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
        log("Google Maps Platform monthly call count is %s for %s.", count, month)
