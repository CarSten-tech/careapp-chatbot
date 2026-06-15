from fastapi import APIRouter

from careapp.api.models import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["infra"])
async def health() -> HealthResponse:
    """Health-Check für Load-Balancer und Monitoring."""
    return HealthResponse(status="ok")
