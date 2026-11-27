"""Аутентификация: вход по логину и паролю, выдача JWT, «кто я».

Пароли хранятся только в виде хеша (PBKDF2), сравнение — с постоянным
временем. В ответе на успешный вход возвращается и токен, и данные
пользователя: фронтенду не нужен второй запрос, чтобы отрисовать шапку.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from deps import CurrentUserDep, SessionDep
from models.entities import User
from models.schemas import LoginIn, TokenOut, UserOut
from services.auth import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut, summary="Вход и выдача JWT")
async def login(payload: LoginIn, session: SessionDep) -> TokenOut:
    user = (
        await session.execute(select(User).where(User.username == payload.username.strip().lower()))
    ).scalar_one_or_none()

    # Одна и та же ошибка на «нет пользователя» и «неверный пароль»:
    # ответ не должен подсказывать, существует ли логин.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token, expires_in = create_access_token(user.username)
    return TokenOut(access_token=token, expires_in=expires_in, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut, summary="Текущий пользователь")
async def me(user: CurrentUserDep) -> UserOut:
    return UserOut.model_validate(user)
