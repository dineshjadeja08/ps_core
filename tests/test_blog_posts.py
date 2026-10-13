from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.catalogue.models import BlogPost


@pytest.fixture
def admin_client():
    user = User.objects.create_user("+919876543299", role=UserRole.ADMIN, is_verified=True, is_staff=True)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def post_data(**changes):
    return {
        "title": "Why an AC may stop cooling",
        "slug": "why-ac-stops-cooling",
        "excerpt": "Common symptoms to record before arranging an AC inspection.",
        "body": "## Check the symptoms\nNote when cooling changed.\n\nAsk a technician to inspect electrical faults.",
        "author_name": "Purple Squad Team",
        "is_published": False,
        **changes,
    }


@pytest.mark.django_db
def test_drafts_are_private_until_published(admin_client, client):
    created = admin_client.post("/api/v1/admin/blog-posts/", post_data(), format="json")
    assert created.status_code == 201
    assert created.data["published_at"] is None
    assert client.get("/api/v1/blog-posts/").data["count"] == 0
    assert client.get("/api/v1/blog-posts/why-ac-stops-cooling/").status_code == 404

    post_id = created.data["id"]
    published = admin_client.patch(f"/api/v1/admin/blog-posts/{post_id}/", {"is_published": True}, format="json")
    assert published.status_code == 200
    assert published.data["published_at"] is not None
    assert client.get("/api/v1/blog-posts/").data["count"] == 1
    assert client.get("/api/v1/blog-posts/why-ac-stops-cooling/").data["body"].startswith("## Check")

    unpublished = admin_client.patch(f"/api/v1/admin/blog-posts/{post_id}/", {"is_published": False}, format="json")
    assert unpublished.status_code == 200
    assert client.get("/api/v1/blog-posts/why-ac-stops-cooling/").status_code == 404


@pytest.mark.django_db
def test_public_blog_excludes_future_publication(client):
    BlogPost.objects.create(**post_data(is_published=True, published_at=timezone.now() + timedelta(days=1)))
    assert client.get("/api/v1/blog-posts/").data["count"] == 0


@pytest.mark.django_db
def test_blog_admin_requires_auth_and_rejects_unsafe_image(admin_client, client):
    assert client.post("/api/v1/admin/blog-posts/", post_data(), content_type="application/json").status_code in (401, 403)
    response = admin_client.post("/api/v1/admin/blog-posts/", post_data(cover_image_url="http://example.com/image.jpg"), format="json")
    assert response.status_code == 400
    assert "cover_image_url" in response.data["error"]["details"]


@pytest.mark.django_db
def test_catalogue_manager_can_edit_blog_posts():
    user = User.objects.create_user("+919876543298", role=UserRole.ADMIN, is_verified=True, is_staff=True)
    user.groups.add(Group.objects.create(name="Catalogue Manager"))
    client = APIClient()
    client.force_authenticate(user=user)
    response = client.post("/api/v1/admin/blog-posts/", post_data(), format="json")
    assert response.status_code == 201
