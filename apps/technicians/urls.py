from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.technicians.views import (
    AdminTechnicianLeaveViewSet,
    AdminTechnicianListView,
    AdminTechnicianDetailView,
    AdminTechnicianOptionsView,
    AdminTechnicianJobsView,
    AdminTechnicianActivityView,
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
    path("admin/technicians/options/", AdminTechnicianOptionsView.as_view(), name="admin-technician-options"),
    path("admin/technicians/<uuid:pk>/", AdminTechnicianDetailView.as_view(), name="admin-technician-detail"),
    path("admin/technicians/<uuid:pk>/jobs/", AdminTechnicianJobsView.as_view(), name="admin-technician-jobs"),
    path("admin/technicians/<uuid:pk>/activities/", AdminTechnicianActivityView.as_view(), name="admin-technician-activities"),
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
