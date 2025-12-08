from fastapi import APIRouter, Depends
from dependency_injector.wiring import inject, Provide
from src.domain.health.service import HealthService
from src.domain.health.module import HealthModule


router = APIRouter(prefix="/health", tags=["health"])


@router.get("", summary="Health check endpoint")
@inject
async def health_check(service: HealthService = Depends(Provide[HealthModule.service]),
                       ) -> dict:
    db_health = await service.check_database_health()
    status = "healthy" if db_health else "unhealthy"
    return {"status": status, "database": db_health}
