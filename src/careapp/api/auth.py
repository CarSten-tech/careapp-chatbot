"""
Auth-Middleware (Layer 6 §2.3 / T4).

`get_auth_context()` baut den `AuthContext` AUS DEM TOKEN — niemals aus dem
Request-Body oder Query-Parametern. Das ist die T4-Garantie auf API-Ebene.

Zwei Modi:
- DEV_AUTH (CAREAPP_DEV_AUTH=true): hardcoded Pilot-AuthContext, kein JWT nötig.
  Nur für lokale Entwicklung und Tests — nie in Produktion setzen.
- PROD: JWT aus dem Bearer-Token validieren (Supabase HS256).
"""

import os
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from careapp.orchestration.state import AuthContext

# Pilot-AuthContext für lokale Entwicklung (DEV_AUTH-Modus)
_DEV_AUTH_CONTEXT = AuthContext(
    tenant_id="careapp-pilot",
    region_id="nrw-kreis-neuss",
    target_group_codes=("patient", "family"),
    consent_granted=True,
    locale="de",
)


def _extract_bearer(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_or_malformed_token")
    return authorization.removeprefix("Bearer ").strip()


async def get_auth_context(request: Request) -> AuthContext:
    """
    FastAPI Dependency: JWT → AuthContext (T4).
    In Tests: Abhängigkeit via app.dependency_overrides ersetzen.
    """
    if os.environ.get("CAREAPP_DEV_AUTH") == "true":
        return _DEV_AUTH_CONTEXT

    token = _extract_bearer(request)
    jwt_secret = os.environ.get("SUPABASE_JWT_SECRET", "")
    if not jwt_secret:
        raise HTTPException(status_code=503, detail="jwt_secret_not_configured")

    try:
        from jose import JWTError, jwt

        payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
        meta: dict = payload.get("app_metadata", {})
        return AuthContext(
            tenant_id=meta.get("tenant_id"),
            region_id=meta.get("region_id"),
            target_group_codes=tuple(meta.get("target_group_codes", [])),
            consent_granted=bool(meta.get("consent_granted", False)),
            locale=str(meta.get("locale", "de")),
        )
    except Exception:
        raise HTTPException(status_code=401, detail="invalid_token")


AuthContextDep = Annotated[AuthContext, Depends(get_auth_context)]
