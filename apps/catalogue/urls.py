from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.catalogue.views import (
    AdminServiceCategoryViewSet,
    AdminServiceImageViewSet,
    AdminServiceViewSet,
    ServiceCategoryListView,
    ServiceDetailView,
    ServiceListView,
)

router = SimpleRouter()
router.register("admin/service-categories", AdminServiceCategoryViewSet, basename="admin-service-category")
router.register("admin/services", AdminServiceViewSet, basename="admin-service")

urlpatterns = [
    path("service-categories/", ServiceCategoryListView.as_view(), name="service-category-list"),
    path("services/", ServiceListView.as_view(), name="service-list"),
    path("services/<slug:slug>/", ServiceDetailView.as_view(), name="service-detail"),
    path(
        "admin/services/<uuid:service_id>/images/",
        AdminServiceImageViewSet.as_view({"get": "list", "post": "create"}),
        name="admin-service-image-list",
    ),
    path(
        "admin/services/<uuid:service_id>/images/<uuid:image_id>/",
        AdminServiceImageViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="admin-service-image-detail",
    ),
] + router.urls
