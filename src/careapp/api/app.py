"""
FastAPI App-Factory (Layer 6).

`create_app()` gibt eine konfigurierte FastAPI-Instanz zurück.
Das Factory-Muster ermöglicht Tests, die App mit überschriebenen
Dependencies zu instanziieren (app.dependency_overrides).

Endpunkte (Chatbot):
  POST   /api/v1/chat
  GET    /api/v1/session/{id}/state
  DELETE /api/v1/session/{id}
  GET    /api/v1/citation/{claim_version_id}
  GET    /api/v1/health

Endpunkte (Admin — Bearer-Token-geschützt):
  GET    /api/v1/admin/stats
  GET    /api/v1/admin/claims
  POST   /api/v1/admin/claims
  GET    /api/v1/admin/claims/{id}
  PATCH  /api/v1/admin/claims/{id}
  POST   /api/v1/admin/claims/{id}/transition
  POST   /api/v1/admin/claims/{id}/approve
  GET    /api/v1/admin/sources
  POST   /api/v1/admin/sources
  GET    /api/v1/admin/sources/{id}/passages
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from careapp.api.routers import admin, chat, citation, health


def create_app() -> FastAPI:
    app = FastAPI(
        title="CareApp Chatbot API",
        description=(
            "Sicherheitskritische Beratungs-API für das deutsche Gesundheits-/Sozialsystem. "
            "Jede fachliche Aussage ist belegbar und wird vor Ausgabe geprüft."
        ),
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # CORS — nur eigene Origins (§2.6)
    allowed_origins_raw = os.environ.get("CAREAPP_ALLOWED_ORIGINS", "http://localhost:3000")
    allowed_origins = [o.strip() for o in allowed_origins_raw.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(citation.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")
    app.include_router(health.router, prefix="/api/v1")

    return app


# Direktstart: uvicorn careapp.api.app:app
app = create_app()
