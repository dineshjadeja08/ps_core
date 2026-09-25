from rest_framework.permissions import BasePermission

from apps.accounts.models import UserRole
from apps.accounts.staff_access import staff_access_allowed
from apps.audit.models import AuditAction
from apps.audit.services import audit_event


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        allowed = bool(user and user.is_authenticated and user.role == UserRole.SUPER_ADMIN)
        if user and user.is_authenticated and user.role == UserRole.ADMIN:
            allowed = staff_access_allowed(user, request)
        if not allowed and getattr(request, "user", None) and request.user.is_authenticated and hasattr(request, "META"):
            audit_event(
                action=AuditAction.PERMISSION_DENIED,
                actor=request.user,
                request=request,
                resource_type="admin_endpoint",
                resource_id=getattr(view, "__class__", type(view)).__name__,
                metadata={"path": getattr(request, "path", "")},
            )
        return allowed


class IsSuperAdminRole(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.SUPER_ADMIN
        )


class IsTechnicianRole(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.TECHNICIAN
        )


class IsObjectOwner(BasePermission):
    owner_field = "user"

    def has_object_permission(self, request, view, obj):
        owner = getattr(obj, self.owner_field, None)
        return owner == request.user
