from urllib.parse import urlencode


def technician_assignment_payload(assignment):
    booking = assignment.booking
    address = booking.address_snapshot if isinstance(booking.address_snapshot, dict) else {}
    customer = booking.customer
    profile = getattr(customer, "customer_profile", None)
    name = getattr(profile, "display_name", "") or " ".join(filter(None, [customer.first_name, customer.last_name])) or "Customer"
    formatted_address = address.get("formatted_address") or ", ".join(
        str(address.get(field) or getattr(booking.address, field, "") or "")
        for field in ("address_line_1", "address_line_2", "area", "city", "state", "postal_code")
        if address.get(field) or getattr(booking.address, field, "")
    )
    latitude = address.get("latitude", booking.address.latitude)
    longitude = address.get("longitude", booking.address.longitude)
    query = f"{latitude},{longitude}" if latitude is not None and longitude is not None else formatted_address
    schedule = f"{booking.service_date.isoformat()} {booking.time_slot.start_time.strftime('%H:%M')}–{booking.time_slot.end_time.strftime('%H:%M')} IST"
    return {
        "assignment_id": str(assignment.id), "technician_id": str(assignment.technician_id),
        "mobile": assignment.technician.phone,
        "template_values": [assignment.technician.display_name, booking.booking_number, booking.service.name,
                            schedule, name, booking.contact_phone or customer.phone_number, formatted_address or "See booking details",
                            f"https://www.google.com/maps/search/?{urlencode({'api': 1, 'query': query})}"],
    }
