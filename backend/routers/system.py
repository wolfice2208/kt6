"""Роутер: здоровье сервиса, принудительный обход и текущая конфигурация."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select, text

from config import get_settings
from deps import BusDep, IngestionDep, ManagerDep, SessionDep
from models.entities import WatchItem
from models.schemas import HealthOut, ScanResultOut

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health", response_model=HealthOut)
async def health(
    session: SessionDep,
    bus: BusDep,
    manager: ManagerDep,
    ingestion: IngestionDep,
) -> HealthOut:
    settings = get_settings()
    database = "ok"
    items_tracked = 0
    try:
        await session.execute(text("SELECT 1"))
        items_tracked = int(
            (await session.execute(select(func.count()).select_from(WatchItem))).scalar_one()
        )
    except Exception:  # noqa: BLE001 - healthcheck обязан отвечать всегда
        database = "error"

    return HealthOut(
        status="ok" if database == "ok" else "degraded",
        version=settings.app_version,
        data_source=settings.data_source,
        region=settings.stalzone_region,
        ingestion_enabled=settings.enable_ingestion,
        scan_interval_seconds=settings.scan_interval_seconds,
        last_scan_at=ingestion.last_scan_at,
        last_scan_duration_ms=ingestion.last_stats.duration_ms if ingestion.last_stats else None,
        scans_total=ingestion.scans_total,
        items_tracked=items_tracked,
        sse_clients=bus.subscriber_count,
        ws_connections=manager.total_connections,
        database=database,
    )


@router.post("/scan", response_model=ScanResultOut)
async def force_scan(ingestion: IngestionDep) -> ScanResultOut:
    stats = await ingestion.scan_once()
    return ScanResultOut(
        scanned=stats.scanned,
        deals=stats.deals,
        alerts=stats.alerts,
        duration_ms=round(stats.duration_ms, 1),
    )


@router.get("/config")
async def public_config() -> dict:
    """Только безопасная часть конфигурации — без токенов и секретов."""
    settings = get_settings()
    return {
        "app_name": settings.app_name,
        "version": settings.app_version,
        "data_source": settings.data_source,
        "region": settings.stalzone_region,
        "fee_pct": settings.fee_pct,
        "scan_interval_seconds": settings.scan_interval_seconds,
        "history_window_days": settings.history_window_days,
        "cors_origins": settings.cors_origin_list,
    }
