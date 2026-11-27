"""Пароли и JWT-токены.

Пароли не хранятся в открытом виде: PBKDF2-HMAC-SHA256 со случайной солью
(стандартная библиотека, без внешних зависимостей). Токен — обычный JWT
(HS256) с полем ``sub`` = логин и сроком жизни из настроек.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from config import get_settings

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 180_000


class TokenError(Exception):
    """Токен отсутствует, просрочен или подписан не нашим ключом."""


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def hash_password(password: str, *, iterations: int = _ITERATIONS) -> str:
    """``pbkdf2_sha256$<итерации>$<соль>$<хеш>`` — самодостаточная строка."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), iterations)
    return f"{_ALGORITHM}${iterations}${salt}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """Сравнение с постоянным временем — без утечки по таймингу."""
    try:
        algorithm, raw_iterations, salt, expected = stored.split("$", 3)
        if algorithm != _ALGORITHM:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("ascii"), int(raw_iterations)
        )
        return hmac.compare_digest(_b64(digest), expected)
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, *, ttl_minutes: int | None = None) -> tuple[str, int]:
    """Возвращает (токен, срок жизни в секундах)."""
    settings = get_settings()
    ttl = ttl_minutes or settings.jwt_ttl_minutes
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=ttl)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "typ": "access",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, ttl * 60


def decode_token(token: str) -> str:
    """Проверяет подпись и срок, возвращает логин. Любая проблема — TokenError."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Срок действия токена истёк") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Некорректный токен") from exc

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise TokenError("В токене нет пользователя")
    return subject
