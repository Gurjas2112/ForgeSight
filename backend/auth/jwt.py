"""
ForgeSight — Supabase JWT verification (design Tier-1). Decodes the GoTrue access token
(audience `authenticated`) into an AuthUser, reading the app role from `app_metadata.role`.
Supports both project signing modes: **asymmetric ES256/RS256 via the project JWKS** (new
default) and **legacy HS256** with the JWT secret. Used by the `current_user` dependency.
"""
from __future__ import annotations

from functools import lru_cache

import jwt
from jwt import PyJWKClient

from backend.config import get_settings
from backend.schemas.agent_models import AuthUser

# Stable UUID for the open/demo (unauthenticated) session — matches the seeded engineer.
DEMO_ENGINEER_ID = "11111111-1111-1111-1111-111111111111"


@lru_cache
def _jwk_client() -> PyJWKClient:
    base = get_settings().supabase_url.rstrip("/")
    return PyJWKClient(f"{base}/auth/v1/.well-known/jwks.json")


def verify_token(token: str) -> AuthUser:
    """Verify a Supabase access token and return the AuthUser. Raises on invalid/expired."""
    s = get_settings()
    alg = (jwt.get_unverified_header(token) or {}).get("alg", "")
    if alg == "HS256":
        payload = jwt.decode(
            token, s.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated")
    else:  # ES256 / RS256 — verify against the project's published JWKS
        key = _jwk_client().get_signing_key_from_jwt(token).key
        payload = jwt.decode(
            token, key, algorithms=["ES256", "RS256"], audience="authenticated")
    role = ((payload.get("app_metadata") or {}).get("role")
            or (payload.get("user_metadata") or {}).get("role") or "engineer")
    if role not in ("engineer", "admin"):
        role = "engineer"
    return AuthUser(id=payload.get("sub") or DEMO_ENGINEER_ID, role=role)


def user_from_header(authorization: str | None) -> AuthUser:
    """Bearer header → AuthUser. Falls back to the demo engineer when no/invalid token, so the
    golden-cache demo stays open without login; a valid token upgrades to the real user + role."""
    if authorization and authorization.lower().startswith("bearer "):
        try:
            return verify_token(authorization.split(" ", 1)[1].strip())
        except Exception:  # noqa: BLE001 — invalid token → demo identity, never a 500
            pass
    return AuthUser(id=DEMO_ENGINEER_ID, role="engineer")
