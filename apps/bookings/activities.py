from apps.audit.models import AuditLog


def actor_name(user):
    if user is None:
        return "System"
    return " ".join(filter(None, [user.first_name, user.last_name])) or user.phone_number


def booking_activities(booking):
    events = [{
        "id": f"booking-{booking.id}", "title": "Booking created",
        "description": booking.booking_number, "actor": actor_name(booking.customer),
        "created_at": booking.created_at,
    }]
    for history in booking.status_history.select_related("changed_by").order_by("-created_at")[:100]:
        events.append({
            "id": f"status-{history.id}", "title": history.to_status.replace("_", " ").title(),
            "description": history.notes, "actor": actor_name(history.changed_by),
            "created_at": history.created_at,
        })
    for log in AuditLog.objects.filter(resource_type="booking", resource_id=str(booking.id)).select_related("actor")[:100]:
        events.append({
            "id": f"audit-{log.id}", "title": log.get_action_display(),
            "description": str(log.metadata.get("notes") or log.metadata.get("reason") or ""),
            "actor": actor_name(log.actor), "created_at": log.created_at,
        })
    for payment in booking.payments.order_by("-updated_at")[:100]:
        events.append({
            "id": f"payment-{payment.id}",
            "title": f"{payment.get_payment_type_display()} · {payment.get_status_display()}",
            "description": f"{payment.currency} {payment.amount} · {payment.get_provider_display()}",
            "actor": "Payment record",
            "created_at": payment.refunded_at or payment.paid_at or payment.updated_at,
        })
    return sorted(events, key=lambda event: (event["created_at"], event["id"]), reverse=True)[:100]
