from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.technicians.views import (
    AdminTechnicianLeaveViewSet,
    AdminTechnicianListView,
    AdminTechnicianDetailView,
    AdminTechnicianOptionsView,
    AdminTechnicianJobsView,
    AdminTechnicianActivityView,
    AdminTechnicianDocumentsView,
    AdminTechnicianDocumentContentView,
    AdminTechnicianDocumentDetailView,
    AdminTechnicianCompanyUsersView,
    AdminTechnicianCompanyUserDetailView,
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
    path("admin/technicians/<uuid:pk>/documents/", AdminTechnicianDocumentsView.as_view(), name="admin-technician-documents"),
    path("admin/technicians/<uuid:pk>/documents/<uuid:document_id>/content/", AdminTechnicianDocumentContentView.as_view(), name="admin-technician-document-content"),
    path("admin/technicians/<uuid:pk>/documents/<uuid:document_id>/", AdminTechnicianDocumentDetailView.as_view(), name="admin-technician-document-detail"),
    path("admin/technicians/<uuid:pk>/company-users/", AdminTechnicianCompanyUsersView.as_view(), name="admin-technician-company-users"),
    path("admin/technicians/<uuid:pk>/company-users/<uuid:user_id>/", AdminTechnicianCompanyUserDetailView.as_view(), name="admin-technician-company-user-detail"),
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
