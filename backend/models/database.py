"""SQLAlchemy: асинхронный движок, фабрика сессий, инициализация схемы."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
engine = create_async_engine(
    _settings.resolved_database_url,
    echo=False,
    future=True,
    # SQLite: ждём освобождения блокировки вместо мгновенной ошибки,
    # потому что писать могут и воркер, и обработчики запросов.
    connect_args={"timeout": 30},
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@event.listens_for(engine.sync_engine, "connect")
def _configure_sqlite(dbapi_connection, _connection_record) -> None:
    """WAL + busy_timeout: параллельные читатели не блокируют воркер."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


async def init_db() -> None:
    """Создаёт каталог данных, таблицы и докатывает недостающие колонки."""
    from models import entities  # noqa: F401  — регистрация метаданных

    _settings.ensure_dirs()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_apply_light_migrations)


def _apply_light_migrations(conn) -> None:
    """Мини-миграции для SQLite: create_all не добавляет колонки в старые БД."""
    rows = conn.exec_driver_sql("PRAGMA table_info(filter_rules)").fetchall()
    columns = {row[1] for row in rows}
    if "item_ids" not in columns:
        conn.exec_driver_sql("ALTER TABLE filter_rules ADD COLUMN item_ids JSON DEFAULT '[]'")


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI-зависимость: сессия БД на один запрос."""
    async with SessionLocal() as session:
        yield session
