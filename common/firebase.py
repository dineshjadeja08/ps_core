from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def get_firebase_app():
    """Return the process-wide Firebase Admin app.

    Cloud Run uses Application Default Credentials from its service identity.
    Non-Google environments can continue to provide a service-account file.
    """
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError as exc:
        raise ImproperlyConfigured("firebase-admin is required for Firebase authentication and FCM.") from exc

    if firebase_admin._apps:
        return firebase_admin.get_app()

    credentials_path = str(getattr(settings, "FIREBASE_CREDENTIALS_PATH", "") or "").strip()
    project_id = str(getattr(settings, "FIREBASE_PROJECT_ID", "") or "").strip()
    options = {"projectId": project_id} if project_id else None

    if credentials_path:
        path = Path(credentials_path).expanduser()
        if not path.is_file():
            raise ImproperlyConfigured(f"Firebase credentials file does not exist: {path}")
        return firebase_admin.initialize_app(credentials.Certificate(str(path)), options=options)

    # In Cloud Run, firebase-admin obtains credentials from the service account
    # attached to the service. No downloadable private key is required.
    return firebase_admin.initialize_app(options=options)
