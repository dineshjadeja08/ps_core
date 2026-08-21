from importlib import import_module

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_health_endpoint(client):
    response = client.get("/api/v1/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response["X-Request-ID"]


@pytest.mark.django_db
def test_swagger_schema_generation(client):
    response = client.get(reverse("schema"))

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/vnd.oai.openapi")
    schema_text = response.content.decode()
    assert "Purple Squad API" in schema_text
    assert "/api/v1/health/" in schema_text


def test_configuration_imports():
    for module_name in (
        "config.settings.base",
        "config.settings.local",
        "config.settings.test",
    ):
        assert import_module(module_name)


@pytest.mark.django_db
def test_standard_404_response(client):
    response = client.get("/api/v1/does-not-exist/")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "Not found.",
            "details": {},
        }
    }
