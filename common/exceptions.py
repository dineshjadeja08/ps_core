from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler


DEFAULT_ERROR_CODES = {
    status.HTTP_400_BAD_REQUEST: "VALIDATION_ERROR",
    status.HTTP_401_UNAUTHORIZED: "AUTHENTICATION_REQUIRED",
    status.HTTP_403_FORBIDDEN: "PERMISSION_DENIED",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
    status.HTTP_429_TOO_MANY_REQUESTS: "THROTTLED",
}


def standard_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None and isinstance(exc, Http404):
        response = Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    if response is None and isinstance(exc, DjangoValidationError):
        details = exc.message_dict if hasattr(exc, "message_dict") else {"non_field_errors": exc.messages}
        response = Response(details, status=status.HTTP_400_BAD_REQUEST)

    if response is None and isinstance(exc, IntegrityError):
        response = Response(
            {"non_field_errors": ["This change conflicts with an existing record or database constraint."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if response is None:
        return None

    code = getattr(exc, "public_code", None) or DEFAULT_ERROR_CODES.get(response.status_code, "API_ERROR")
    message = _extract_message(response.data)

    response.data = {
        "error": {
            "code": code,
            "message": message,
            "details": _extract_details(response.data),
        }
    }
    return response


def _extract_message(data):
    if isinstance(data, (str, exceptions.ErrorDetail)):
        return str(data)
    if isinstance(data, dict):
        detail = data.get("detail")
        if detail is not None:
            return _extract_message(detail)
        for value in data.values():
            if value not in (None, "", [], {}):
                return _extract_message(value)
        return "Validation error."
    if isinstance(data, (list, tuple)):
        return _extract_message(data[0]) if data else "Validation error."
    return "An error occurred."


def _extract_details(data):
    if isinstance(data, dict) and set(data.keys()) == {"detail"}:
        return {}
    return data
