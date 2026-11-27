"""Общие зависимости FastAPI: сессия БД, текущий пользователь, сервисы.

Идентификация — по JWT в заголовке ``Authorization: Bearer <token>``.
Токен выдаёт ``POST /api/auth/login``; логика подписи и проверки лежит
в ``services/auth.py``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import get_session
from models.entities import User
from services.auth import TokenError, decode_token
from services.connections import ConnectionManager
from services.events import EventBus
from services.ingestion import IngestionService

# auto_error=False: сами решаем, какую ошибку отдать (нужен единый 401).
bearer_scheme = HTTPBearer(auto_error=False, description="JWT из POST /api/auth/login")


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """Проверяет токен и достаёт пользователя из БД."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        username = decode_token(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = (await session.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def current_user_id(user: Annotated[User, Depends(get_current_user)]) -> str:
    """Логин текущего пользователя — он же ``user_id`` во всех таблицах."""
    return user.username


def get_ingestion(request: Request) -> IngestionService:
    return request.app.state.ingestion


def get_bus(request: Request) -> EventBus:
    return request.app.state.bus


def get_manager(request: Request) -> ConnectionManager:
    return request.app.state.manager


SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
UserDep = Annotated[str, Depends(current_user_id)]
IngestionDep = Annotated[IngestionService, Depends(get_ingestion)]
BusDep = Annotated[EventBus, Depends(get_bus)]
ManagerDep = Annotated[ConnectionManager, Depends(get_manager)]
