import logging
import time
import uuid

from django.conf import settings
from django.http import JsonResponse

logger = logging.getLogger("purple_squad.request")
error_logger = logging.getLogger("purple_squad.errors")


class ApiExceptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if not request.path.startswith("/api/"):
            return None

        request_id = getattr(request, "request_id", "")
        error_logger.exception(
            "api_unhandled_exception path=%s method=%s request_id=%s",
            request.path,
            request.method,
            request_id,
        )
        return JsonResponse(
            {
                "error": {
                    "code": "SERVER_ERROR",
                    "message": "Purple Squad backend hit a server error. Check backend logs with this request ID.",
                    "request_id": request_id,
                }
            },
            status=500,
        )


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started_at = time.monotonic()
        request_id = request.META.get(settings.REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.request_id = request_id

        response = self.get_response(request)
        response["X-Request-ID"] = request_id

        duration_ms = int((time.monotonic() - started_at) * 1000)
        user_id = getattr(getattr(request, "user", None), "id", None)
        logger.info(
            "request_complete method=%s path=%s status_code=%s request_id=%s user_id=%s duration_ms=%s",
            request.method,
            request.path,
            response.status_code,
            request_id,
            user_id,
            duration_ms,
        )
        return response
