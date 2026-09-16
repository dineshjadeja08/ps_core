from rest_framework.test import APIClient


def test_booking_preflight_allows_idempotency_key(settings):
    origin = "https://purple-squad.example"
    settings.CORS_ALLOWED_ORIGINS = [origin]

    response = APIClient().options(
        "/api/v1/bookings/",
        HTTP_ORIGIN=origin,
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization, content-type, idempotency-key",
    )

    assert response.status_code == 200
    assert response["Access-Control-Allow-Origin"] == origin
    allowed_headers = {value.strip().lower() for value in response["Access-Control-Allow-Headers"].split(",")}
    assert "idempotency-key" in allowed_headers
