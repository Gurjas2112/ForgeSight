"""
ForgeSight — Supabase GoTrue admin helper. Creates **pre-confirmed** users with an app role via the
service-role Admin API (sidesteps email-confirmation friction for the demo), and mirrors the role
into `profiles`. Used by `POST /auth/signup` and the account seeder.
"""
from __future__ import annotations

import requests

from backend.config import get_settings

_TIMEOUT = 15


class DuplicateUserError(RuntimeError):
    """Raised when a signup targets an email that already has a Supabase account."""


def create_user(email: str, password: str, role: str, full_name: str | None = None) -> dict:
    """Create a confirmed Supabase user with app_metadata.role. Returns {id, email, role}.

    Requires SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY. Raises DuplicateUserError when the email
    already exists (so the route can return a clean 409), RuntimeError on any other hard failure.
    """
    s = get_settings()
    if not (s.supabase_url and s.supabase_service_role_key):
        raise RuntimeError("Supabase URL / service-role key not configured")
    if role not in ("engineer", "admin"):
        role = "engineer"
    base = s.supabase_url.rstrip("/")
    headers = {"apikey": s.supabase_service_role_key,
               "Authorization": f"Bearer {s.supabase_service_role_key}",
               "Content-Type": "application/json"}
    body = {"email": email, "password": password, "email_confirm": True,
            "app_metadata": {"role": role, "provider": "email", "providers": ["email"]},
            "user_metadata": {"full_name": full_name or email.split("@")[0]}}
    r = requests.post(f"{base}/auth/v1/admin/users", json=body, headers=headers, timeout=_TIMEOUT)
    if r.status_code in (200, 201):
        uid = r.json().get("id")
    elif r.status_code in (409, 422) or "already" in r.text.lower():
        raise DuplicateUserError("an account with this email already exists")
    else:
        raise RuntimeError(f"signup failed: {r.status_code} {r.text[:200]}")
    return {"id": uid, "email": email, "role": role}
