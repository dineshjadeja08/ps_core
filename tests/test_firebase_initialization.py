from unittest.mock import Mock

import firebase_admin

from common.firebase import get_firebase_app


def test_firebase_uses_application_default_credentials_without_key_file(monkeypatch, settings):
    expected_app = object()
    initialize_app = Mock(return_value=expected_app)
    monkeypatch.setattr(firebase_admin, "_apps", {})
    monkeypatch.setattr(firebase_admin, "initialize_app", initialize_app)
    settings.FIREBASE_CREDENTIALS_PATH = ""
    settings.FIREBASE_PROJECT_ID = "purplesquad"

    assert get_firebase_app() is expected_app
    initialize_app.assert_called_once_with(options={"projectId": "purplesquad"})
