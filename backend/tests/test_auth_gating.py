"""Auth hardening — public signup must not be able to self-assign `admin`.

The `/auth/signup` route downgrades a requested `admin` role to `engineer` unless the caller
presents a valid admin Bearer token, using `user_from_header` as the authority check. These tests
pin that authority check: an absent or invalid token resolves to a non-admin engineer, so the
downgrade always fires for unauthenticated callers. (No DB / no live Supabase required.)"""

from __future__ import annotations

from backend.auth.jwt import user_from_header


def _effective_signup_role(requested: str, authorization: str | None) -> str:
    """Mirror of the route's gating policy (kept in lock-step with server.signup)."""
    if requested == "admin" and user_from_header(authorization).role != "admin":
        return "engineer"
    return requested


def test_no_token_is_engineer():
    assert user_from_header(None).role == "engineer"


def test_invalid_token_is_engineer():
    assert user_from_header("Bearer not-a-real-jwt").role == "engineer"


def test_public_admin_signup_is_downgraded():
    assert _effective_signup_role("admin", None) == "engineer"
    assert _effective_signup_role("admin", "Bearer garbage") == "engineer"


def test_engineer_signup_passes_through():
    assert _effective_signup_role("engineer", None) == "engineer"
