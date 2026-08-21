from django.http import JsonResponse
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthResponseSerializer(serializers.Serializer):
    status = serializers.CharField()


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        summary="Health check",
        description="Returns a lightweight health response for uptime probes.",
        responses={status.HTTP_200_OK: HealthResponseSerializer},
        examples=[
            OpenApiExample(
                "Healthy",
                value={"status": "ok"},
                response_only=True,
                status_codes=["200"],
            )
        ],
    )
    def get(self, request):
        return Response({"status": "ok"})


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
