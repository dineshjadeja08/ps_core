from apps.audit.models import AuditLog
from apps.bookings.activities import actor_name


def technician_activities(technician):
    events = [{
        "id": f"technician-{technician.id}", "title": "Technician profile created",
        "description": technician.employee_code, "actor": "System", "created_at": technician.created_at,
    }]
    for log in AuditLog.objects.filter(resource_type="technician", resource_id=str(technician.id)).select_related("actor")[:100]:
        events.append({
            "id": f"audit-{log.id}", "title": log.get_action_display(),
            "description": " · ".join(str(log.metadata[key]) for key in ("verification", "availability", "is_active") if key in log.metadata),
            "actor": actor_name(log.actor), "created_at": log.created_at,
        })
    for assignment in technician.assignments.select_related("booking", "assigned_by").order_by("-assigned_at")[:100]:
        events.append({
            "id": f"assignment-{assignment.id}", "title": "Booking assigned",
            "description": assignment.booking.booking_number, "actor": actor_name(assignment.assigned_by),
            "created_at": assignment.assigned_at,
        })
        if assignment.unassigned_at:
            events.append({
                "id": f"unassignment-{assignment.id}", "title": "Assignment ended",
                "description": assignment.booking.booking_number, "actor": "See booking activity for actor",
                "created_at": assignment.unassigned_at,
            })
    return sorted(events, key=lambda event: (event["created_at"], event["id"]), reverse=True)[:100]
