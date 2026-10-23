import uuid
from pathlib import Path

import requests
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.exceptions import ImproperlyConfigured


PRIVATE_LOCAL_STORAGE = FileSystemStorage(
    location=Path(settings.BASE_DIR) / ".private-media",
    base_url=None,
)


def store_private_document(uploaded_file):
    """Store an authenticated Cloudinary asset in production, private local file in development."""
    if getattr(settings, "USE_CLOUDINARY_MEDIA", False):
        import cloudinary.uploader

        extension = Path(uploaded_file.name).suffix.lower()
        resource_type = "image" if uploaded_file.content_type.startswith("image/") else "raw"
        public_id = f"technicians/private-documents/{uuid.uuid4().hex}{extension if resource_type == 'raw' else ''}"
        uploaded_file.seek(0)
        result = cloudinary.uploader.upload(
            uploaded_file,
            public_id=public_id,
            resource_type=resource_type,
            type="authenticated",
            overwrite=False,
            use_filename=False,
        )
        return "cloudinary", result["public_id"], resource_type

    path = PRIVATE_LOCAL_STORAGE.save(f"technicians/{uuid.uuid4().hex}/{Path(uploaded_file.name).name}", uploaded_file)
    return "local", path, "raw"


def delete_private_document(document):
    if document.storage_backend == "local":
        PRIVATE_LOCAL_STORAGE.delete(document.storage_public_id)
        return
    if document.storage_backend == "cloudinary":
        import cloudinary.uploader

        cloudinary.uploader.destroy(
            document.storage_public_id,
            resource_type=document.storage_resource_type,
            type="authenticated",
            invalidate=True,
        )
        return
    raise ImproperlyConfigured("Unknown private document storage backend.")


def read_private_document(document):
    if document.storage_backend == "local":
        with PRIVATE_LOCAL_STORAGE.open(document.storage_public_id, "rb") as document_file:
            return document_file.read()
    if document.storage_backend == "cloudinary":
        import cloudinary.utils

        url, _ = cloudinary.utils.cloudinary_url(
            document.storage_public_id,
            resource_type=document.storage_resource_type,
            type="authenticated",
            sign_url=True,
            secure=True,
        )
        response = requests.get(url, timeout=(5, 30))
        response.raise_for_status()
        return response.content
    raise ImproperlyConfigured("Unknown private document storage backend.")
