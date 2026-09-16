from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.scheduling.views import AdminScheduleClosureViewSet, AdminTimeSlotViewSet, SlotListView

router = DefaultRouter()
router.register("admin/time-slots", AdminTimeSlotViewSet, basename="admin-time-slot")
router.register("admin/schedule-closures", AdminScheduleClosureViewSet, basename="admin-schedule-closure")

urlpatterns = [
    path("", include(router.urls)),
    path("slots/", SlotListView.as_view(), name="slot-list"),
]
