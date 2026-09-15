from importlib import import_module

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_health_endpoint(client):
    response = client.get("/api/v1/health/")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "migrations": "ok", "cache": "ok"},
    }
    assert response["X-Request-ID"]


@pytest.mark.django_db
def test_health_endpoint_reports_pending_migrations(client, monkeypatch):
    class FakeGraph:
        @staticmethod
        def leaf_nodes():
            return [("accounts", "9999_pending")]

    class FakeLoader:
        graph = FakeGraph()

    class FakeExecutor:
        loader = FakeLoader()

        def __init__(self, connection):
            self.connection = connection

        @staticmethod
        def migration_plan(nodes):
            return [(nodes[0], False)]

    monkeypatch.setattr("common.views.MigrationExecutor", FakeExecutor)
    response = client.get("/api/v1/health/")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["checks"]["migrations"] == "pending"


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
