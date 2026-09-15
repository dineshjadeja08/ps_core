from django.http import JsonResponse
from django.core.cache import cache
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    checks = serializers.DictField(child=serializers.CharField())


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        summary="Health check",
        description="Checks database connectivity, migration state, and the shared cache used for throttling.",
        responses={status.HTTP_200_OK: HealthResponseSerializer, status.HTTP_503_SERVICE_UNAVAILABLE: HealthResponseSerializer},
        examples=[
            OpenApiExample(
                "Healthy",
                value={"status": "ok", "checks": {"database": "ok", "migrations": "ok", "cache": "ok"}},
                response_only=True,
                status_codes=["200"],
            )
        ],
    )
    def get(self, request):
        checks = {"database": "ok", "migrations": "ok", "cache": "ok"}
        healthy = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            checks["database"] = "unavailable"
            checks["migrations"] = "unknown"
            healthy = False
        else:
            try:
                executor = MigrationExecutor(connection)
                pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
                if pending:
                    checks["migrations"] = "pending"
                    healthy = False
            except Exception:
                checks["migrations"] = "unknown"
                healthy = False
        try:
            cache_key = "health:cache"
            cache.set(cache_key, "ok", timeout=10)
            if cache.get(cache_key) != "ok":
                raise RuntimeError("Cache read-after-write failed")
        except Exception:
            checks["cache"] = "unavailable"
            healthy = False
        response_status = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response({"status": "ok" if healthy else "degraded", "checks": checks}, status=response_status)


def not_found(request, exception):
    return JsonResponse(
        {
            "error": {
                "code": "NOT_FOUND",
                "message": "Not found.",
                "details": {},
            }
        },
        status=status.HTTP_404_NOT_FOUND,
    )
