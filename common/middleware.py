import logging
import time
import uuid

from django.conf import settings

logger = logging.getLogger("purple_squad.request")


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
