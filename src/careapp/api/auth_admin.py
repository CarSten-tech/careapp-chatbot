"""
Admin-Auth (Layer 6 — redaktionelles Backend).

Pilot: statisches Bearer-Token aus CAREAPP_ADMIN_TOKEN.
Produktiv: durch Supabase-Row-Level-Security + Rollen ersetzen.
"""

import os

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=True)


def require_admin(
    creds: HTTPAuthorizationCredentials = Security(_bearer),
) -> None:
    token = os.environ.get("CAREAPP_ADMIN_TOKEN", "")
    if not token:
        raise HTTPException(status_code=503, detail="admin_not_configured")
    if creds.credentials != token:
        raise HTTPException(status_code=401, detail="admin_unauthorized")
