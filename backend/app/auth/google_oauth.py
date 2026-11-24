import requests
from google.auth.transport.requests import Request
from google.oauth2 import id_token

from app.core.config import settings


GOOGLE_AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def build_google_authorization_url(state: str, nonce: str) -> str:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise RuntimeError("Google OAuth is not configured.")
    from urllib.parse import urlencode

    params = urlencode({
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "prompt": "select_account",
    })
    return f"{GOOGLE_AUTHORIZATION_URL}?{params}"


def exchange_google_code(code: str, expected_nonce: str) -> dict:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise RuntimeError("Google OAuth is not configured.")

    response = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    if not response.ok:
        raise ValueError("Google authorization code exchange failed.")
    token_response = response.json()
    encoded_id_token = token_response.get("id_token")
    if not encoded_id_token:
        raise ValueError("Google did not return an ID token.")

    claims = id_token.verify_oauth2_token(
        encoded_id_token,
        Request(),
        settings.GOOGLE_CLIENT_ID,
    )
    if claims.get("nonce") != expected_nonce:
        raise ValueError("Google ID token nonce did not match.")
    if not claims.get("email") or claims.get("email_verified") is not True:
        raise ValueError("Google account email is not verified.")
    return claims
