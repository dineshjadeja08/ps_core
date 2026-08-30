from django.urls import path
from django.urls.conf import include

from common.views import HealthCheckView

urlpatterns = [
    path("auth/", include("apps.accounts.urls")),
    path("", include("apps.accounts.admin_urls")),
    path("health/", HealthCheckView.as_view(), name="health"),
    path("", include("apps.catalogue.urls")),
    path("", include("apps.locations.urls")),
    path("", include("apps.scheduling.urls")),
    path("", include("apps.bookings.urls")),
    path("", include("apps.payments.urls")),
    path("", include("apps.technicians.urls")),
    path("", include("apps.reviews.urls")),
    path("", include("apps.operations.urls")),
    path("", include("apps.notifications.urls")),
    path("", include("apps.audit.urls")),
]
