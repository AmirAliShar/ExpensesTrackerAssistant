import pytest
from fastapi import HTTPException
from app.auth.service import (
    normalize_email,
    get_password_hash,
    verify_password,
    create_access_token,
    verify_user_ownership,
)
from app.memory.checkpointer import get_scoped_thread_id


def test_normalize_email():
    """Verify email normalization handles casing and whitespace."""
    assert normalize_email("  User.Test@Antigravity.IO  ") == "user.test@antigravity.io"
    assert normalize_email("John.Doe@Gmail.com") == "john.doe@gmail.com"


def test_password_hashing_and_verification():
    """Verify bcrypt hash generation and validation."""
    pwd = "SecureSecretPassword123!"
    hashed = get_password_hash(pwd)

    assert hashed != pwd
    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_user_ownership_verification_blocks_unauthorized_access():
    """Verify cross-tenant resource manipulation raises HTTP 403 Forbidden."""
    # Authorized access (same user)
    verify_user_ownership(resource_user_id=42, current_user_id=42, resource_name="Transaction")

    # Unauthorized access (different user)
    with pytest.raises(HTTPException) as exc_info:
        verify_user_ownership(resource_user_id=99, current_user_id=42, resource_name="Transaction")
    assert exc_info.value.status_code == 403
    assert "Access denied" in exc_info.value.detail


def test_scoped_thread_id_enforces_user_prefix():
    """Verify thread identifiers are strictly scoped to the authenticated user ID."""
    # User 5 default thread
    t1 = get_scoped_thread_id(user_id=5, raw_thread_id=None)
    assert t1 == "user_5_default"

    # User 5 custom thread
    t2 = get_scoped_thread_id(user_id=5, raw_thread_id="finance_session")
    assert t2 == "user_5_finance_session"

    # Adversary User 5 trying to supply User 10 thread
    t3 = get_scoped_thread_id(user_id=5, raw_thread_id="user_10_secret")
    assert t3 == "user_5_secret"
    assert "user_10" not in t3
