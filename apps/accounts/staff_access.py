from dataclasses import dataclass


@dataclass(frozen=True)
class StaffAccessRule:
    path_prefix: str
    methods: frozenset[str]


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
WRITE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH"})
ALL_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"})


STAFF_ACCESS_PROFILES = {
    "Operations Admin": {
        "description": "Manage daily leads, customers, bookings, work orders, technicians, schedules, and service areas.",
        "rules": (
            StaffAccessRule("/api/v1/admin/dashboard/", SAFE_METHODS),
            StaffAccessRule("/api/v1/admin/search/", SAFE_METHODS),
            StaffAccessRule("/api/v1/admin/reports/", SAFE_METHODS),
            StaffAccessRule("/api/v1/admin/leads/", WRITE_METHODS),
            StaffAccessRule("/api/v1/admin/customers/", WRITE_METHODS),
            StaffAccessRule("/api/v1/admin/bookings/", WRITE_METHODS),
            StaffAccessRule("/api/v1/admin/work-orders/", WRITE_METHODS),
            StaffAccessRule("/api/v1/admin/notifications/", WRITE_METHODS),
            StaffAccessRule("/api/v1/admin/technicians/", WRITE_METHODS),
            StaffAccessRule("/api/v1/admin/technician-leaves/", WRITE_METHODS),
            StaffAccessRule("/api/v1/admin/time-slots/", ALL_METHODS),
            StaffAccessRule("/api/v1/admin/schedule-closures/", ALL_METHODS),
            StaffAccessRule("/api/v1/admin/service-areas/", ALL_METHODS),
        ),
    },
    "Customer Support": {
        "description": "Handle customers and leads, view bookings, and manage customer notifications.",
        "rules": (
            StaffAccessRule("/api/v1/admin/dashboard/", SAFE_METHODS),
            StaffAccessRule("/api/v1/admin/search/", SAFE_METHODS),
            StaffAccessRule("/api/v1/admin/leads/", WRITE_METHODS),
            StaffAccessRule("/api/v1/admin/customers/", WRITE_METHODS),
            StaffAccessRule("/api/v1/admin/bookings/", SAFE_METHODS),
            StaffAccessRule("/api/v1/admin/notifications/", WRITE_METHODS),
        ),
    },
    "Catalogue Manager": {
        "description": "Manage categories, services, packages, FAQs, banners, and homepage carousel content.",
        "rules": (
            StaffAccessRule("/api/v1/admin/dashboard/", SAFE_METHODS),
            StaffAccessRule("/api/v1/admin/service-categories/", ALL_METHODS),
            StaffAccessRule("/api/v1/admin/services/", ALL_METHODS),
            StaffAccessRule("/api/v1/admin/packages/", ALL_METHODS),
            StaffAccessRule("/api/v1/admin/faqs/", ALL_METHODS),
            StaffAccessRule("/api/v1/admin/homepage-banners/", ALL_METHODS),
        ),
    },
    "Finance": {
        "description": "View bookings, manage payments and refunds, and access financial reports.",
        "rules": (
            StaffAccessRule("/api/v1/admin/dashboard/", SAFE_METHODS),
            StaffAccessRule("/api/v1/admin/reports/", SAFE_METHODS),
            StaffAccessRule("/api/v1/admin/bookings/", SAFE_METHODS),
            StaffAccessRule("/api/v1/admin/payments/", WRITE_METHODS),
        ),
    },
    "Technician Coordinator": {
        "description": "Coordinate technicians, assignments, work orders, leave, and booking schedules.",
        "rules": (
            StaffAccessRule("/api/v1/admin/dashboard/", SAFE_METHODS),
            StaffAccessRule("/api/v1/admin/search/", SAFE_METHODS),
            StaffAccessRule("/api/v1/admin/bookings/", WRITE_METHODS),
            StaffAccessRule("/api/v1/admin/work-orders/", WRITE_METHODS),
            StaffAccessRule("/api/v1/admin/technicians/", WRITE_METHODS),
            StaffAccessRule("/api/v1/admin/technician-leaves/", WRITE_METHODS),
            StaffAccessRule("/api/v1/admin/time-slots/", ALL_METHODS),
            StaffAccessRule("/api/v1/admin/schedule-closures/", ALL_METHODS),
        ),
    },
}


def staff_access_allowed(user, request) -> bool:
    if not getattr(user, "is_staff", True):
        return False
    groups = getattr(user, "groups", None)
    if groups is None:
        return True
    group_names = set(groups.values_list("name", flat=True))
    if not group_names or "Super Admin" in group_names:
        return True
    path = request.path
    method = request.method.upper()
    return any(
        path.startswith(rule.path_prefix) and method in rule.methods
        for group_name in group_names
        for rule in STAFF_ACCESS_PROFILES.get(group_name, {}).get("rules", ())
    )
