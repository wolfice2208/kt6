"""Точка входа FastAPI-приложения.

Структура проекта:
    main.py      — создание приложения, lifespan, CORS, подключение роутеров
    config.py    — настройки из .env
    deps.py      — общие зависимости (сессия БД, текущий пользователь по JWT)
    models/      — ORM-модели, схемы Pydantic, подключение к БД
    routers/     — HTTP-эндпоинты по доменам
    services/    — бизнес-логика: клиент API, расчёт цены, экономика сделки, JWT
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from models.database import init_db
from routers import api_router
from seed import seed_demo_trades, seed_users, seed_watchlist
from services.connections import ConnectionManager
from services.events import EventBus
from services.ingestion import IngestionService
from services.stalzone_client import build_source

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    await init_db()

    bus = EventBus()
    manager = ConnectionManager()
    source = build_source(settings)
    ingestion = IngestionService(settings, source, bus, manager)

    app.state.settings = settings
    app.state.bus = bus
    app.state.manager = manager
    app.state.ingestion = ingestion

    if settings.seed_demo_users:
        await seed_users()
    await seed_watchlist(source)
    if settings.seed_demo_trades:
        await seed_demo_trades()

    if settings.enable_ingestion:
        await ingestion.start()
    else:
        # Воркер выключен — делаем один обход, чтобы интерфейс был не пустым.
        try:
            await ingestion.scan_once()
        except Exception:  # noqa: BLE001 - старт не должен падать из-за источника
            logger.exception("Первый обход не удался")

    logger.info(
        "Сервис запущен: source=%s, region=%s, CORS=%s",
        settings.data_source,
        settings.stalzone_region,
        ", ".join(settings.cors_origin_list),
    )
    try:
        yield
    finally:
        await ingestion.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Мониторинг аукциона STALZONE: live-лента выгодных лотов, каталог, "
            "калькулятор выгоды и журнал проведённых сделок с расчётом ROI."
        ),
        lifespan=lifespan,
    )

    # CORS настраивается через .env: адреса фронтенда не зашиты в код.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/", tags=["system"])
    async def root() -> dict[str, str]:
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "api": settings.api_prefix,
            "auth": f"{settings.api_prefix}/auth/login",
            "trades": f"{settings.api_prefix}/trades",
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="debug" if get_settings().debug else "info",
    )
