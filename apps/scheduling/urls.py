from django.urls import path

from apps.scheduling.views import SlotListView

urlpatterns = [
    path("slots/", SlotListView.as_view(), name="slot-list"),
]
