from django.urls import path

from apps.technicians.views import AssignTechnicianView

urlpatterns = [
    path(
        "admin/bookings/<uuid:booking_id>/assign-technician/",
        AssignTechnicianView.as_view(),
        name="admin-booking-assign-technician",
    ),
]
