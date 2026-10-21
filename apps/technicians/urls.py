from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.technicians.views import (
    AdminTechnicianLeaveViewSet,
    AdminJobPhotoListView,
    AdminTechnicianKycView,
    TechnicianDocumentDetailView,
    TechnicianDocumentListView,
    TechnicianKycSubmitView,
    TechnicianSkillListView,
    AdminTechnicianListView,
    AdminTechnicianDetailView,
    AdminTechnicianOptionsView,
    AdminTechnicianJobsView,
    AdminTechnicianActivityView,
    AssignTechnicianView,
    RemoveTechnicianAssignmentView,
    TechnicianJobViewSet,
    TechnicianSelfEarningsView,
    TechnicianSelfLeaveViewSet,
    TechnicianSelfPerformanceView,
    TechnicianSelfProfileView,
    TechnicianSelfReviewListView,
)

router = DefaultRouter()
router.register("technician/jobs", TechnicianJobViewSet, basename="technician-job")
router.register("technician/leaves", TechnicianSelfLeaveViewSet, basename="technician-leave")
router.register("admin/technician-leaves", AdminTechnicianLeaveViewSet, basename="admin-technician-leave")

urlpatterns = [
    path("", include(router.urls)),
    path("technician/skills/", TechnicianSkillListView.as_view(), name="technician-skills"),
    path("technician/documents/", TechnicianDocumentListView.as_view(), name="technician-documents"),
    path("technician/documents/<uuid:document_id>/", TechnicianDocumentDetailView.as_view(), name="technician-document-detail"),
    path("technician/kyc/submit/", TechnicianKycSubmitView.as_view(), name="technician-kyc-submit"),
    path("admin/technicians/<uuid:technician_id>/kyc/", AdminTechnicianKycView.as_view(), name="admin-technician-kyc"),
    path("technician/profile/", TechnicianSelfProfileView.as_view(), name="technician-profile"),
    path("technician/reviews/", TechnicianSelfReviewListView.as_view(), name="technician-reviews"),
    path("technician/earnings/", TechnicianSelfEarningsView.as_view(), name="technician-earnings"),
    path("technician/performance/", TechnicianSelfPerformanceView.as_view(), name="technician-performance"),
    path("admin/bookings/<uuid:booking_id>/photos/", AdminJobPhotoListView.as_view(), name="admin-booking-photos"),
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
