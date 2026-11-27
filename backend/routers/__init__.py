"""Сборка REST-роутеров под общим префиксом /api."""

from fastapi import APIRouter

from routers import alerts, auth, catalog, deals, filters, items, system, trades

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(catalog.router)
api_router.include_router(items.router)
api_router.include_router(deals.router)
api_router.include_router(filters.router)
api_router.include_router(alerts.router)
api_router.include_router(trades.router)

__all__ = ["api_router"]
