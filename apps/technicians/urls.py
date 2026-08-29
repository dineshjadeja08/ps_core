from django.urls import path

from apps.technicians.views import AdminTechnicianListView, AssignTechnicianView, RemoveTechnicianAssignmentView

urlpatterns = [
    path("admin/technicians/", AdminTechnicianListView.as_view(), name="admin-technician-list"),
    path(
        "admin/bookings/<uuid:booking_id>/assign-technician/",
        AssignTechnicianView.as_view(),
        name="admin-booking-assign-technician",
    ),
    path(
        "admin/bookings/<uuid:booking_id>/remove-technician/",
        RemoveTechnicianAssignmentView.as_view(),
        name="admin-booking-remove-technician",
    ),
]
