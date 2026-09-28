from django.conf import settings
from django.contrib import admin
from django.conf.urls.static import static
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from apps.accounts.views import FirebaseLoginView
from apps.notifications.views import DeviceTokenRegisterView

urlpatterns = [
    path("api/v1/", include("config.v1_urls")),
    path("api/auth/firebase-login/", FirebaseLoginView.as_view(), name="firebase-login"),
    path("api/devices/register/", DeviceTokenRegisterView.as_view(), name="device-register-unversioned"),
]

if settings.ENABLE_DJANGO_ADMIN:
    urlpatterns += [path("admin/", admin.site.urls)]

if settings.SHOW_API_DOCS:
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
        path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    ]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = "common.views.not_found"
