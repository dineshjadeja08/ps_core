from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.technicians.views import (
    AdminTechnicianLeaveViewSet,
    AdminTechnicianListView,
    AssignTechnicianView,
    RemoveTechnicianAssignmentView,
    TechnicianJobViewSet,
)

router = DefaultRouter()
router.register("technician/jobs", TechnicianJobViewSet, basename="technician-job")
router.register("admin/technician-leaves", AdminTechnicianLeaveViewSet, basename="admin-technician-leave")

urlpatterns = [
    path("", include(router.urls)),
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
