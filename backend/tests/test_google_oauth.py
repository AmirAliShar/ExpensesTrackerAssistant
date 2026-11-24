from urllib.parse import parse_qs, urlparse
from unittest.mock import MagicMock

import pytest
from fastapi import Request

from app.auth.google_oauth import build_google_authorization_url, exchange_google_code
from app.api.router import google_auth_callback, google_auth_start
from app.core.config import settings


def test_authorization_url_includes_state_nonce_and_expected_redirect(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(
        settings,
        "GOOGLE_REDIRECT_URI",
        "https://api.example.test/api/auth/google/callback",
    )

    parsed = urlparse(build_google_authorization_url("opaque-state", "opaque-nonce"))
    params = parse_qs(parsed.query)
    assert parsed.netloc == "accounts.google.com"
    assert params["client_id"] == ["client-id"]
    assert params["redirect_uri"] == ["https://api.example.test/api/auth/google/callback"]
    assert params["state"] == ["opaque-state"]
    assert params["nonce"] == ["opaque-nonce"]


def test_google_code_exchange_verifies_nonce_and_verified_email(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "client-secret")
    fake_response = MagicMock(ok=True)
    fake_response.json.return_value = {"id_token": "signed-id-token"}
    post = MagicMock(return_value=fake_response)
    monkeypatch.setattr("app.auth.google_oauth.requests.post", post)
    monkeypatch.setattr(
        "app.auth.google_oauth.id_token.verify_oauth2_token",
        lambda token, request, audience: {
            "nonce": "nonce-123",
            "email": "verified@example.com",
            "email_verified": True,
        },
    )

    claims = exchange_google_code("authorization-code", "nonce-123")
    assert claims["email"] == "verified@example.com"
    assert post.call_args.kwargs["timeout"] == 10


def test_google_exchange_rejects_mismatched_nonce(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "client-secret")
    fake_response = MagicMock(ok=True)
    fake_response.json.return_value = {"id_token": "signed-id-token"}
    monkeypatch.setattr("app.auth.google_oauth.requests.post", lambda *args, **kwargs: fake_response)
    monkeypatch.setattr(
        "app.auth.google_oauth.id_token.verify_oauth2_token",
        lambda *args, **kwargs: {
            "nonce": "other-nonce",
            "email": "verified@example.com",
            "email_verified": True,
        },
    )

    with pytest.raises(ValueError, match="nonce"):
        exchange_google_code("authorization-code", "expected-nonce")


def test_authorization_url_rejects_missing_credentials(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", None)
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", None)
    with pytest.raises(RuntimeError, match="not configured"):
        build_google_authorization_url("state", "nonce")


def test_google_start_without_credentials_redirects_with_notice(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", None)
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", None)
    response = google_auth_start()
    assert response.status_code == 307
    assert "oauth_error=google_not_configured" in response.headers["location"]


def test_google_callback_rejects_missing_oauth_state():
    request = Request({
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/auth/google/callback",
        "raw_path": b"/api/auth/google/callback",
        "query_string": b"",
        "headers": [],
        "server": ("localhost", 8000),
        "client": ("127.0.0.1", 50000),
    })
    response = google_auth_callback(
        request=request,
        code="authorization-code",
        state="attacker-controlled",
    )
    assert "oauth_error=google_state_invalid" in response.headers["location"]
