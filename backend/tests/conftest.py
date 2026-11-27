"""Общая настройка тестов: временная БД, поднятое приложение, токен демо-пользователя.

Переменные окружения выставляются до импорта ``main``: движок SQLAlchemy
создаётся на этапе импорта модуля, поэтому менять настройки позже бессмысленно.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
_TMP_ROOT = _BACKEND / ".pytest_tmp"
_TMP_ROOT.mkdir(parents=True, exist_ok=True)
_RUN_DIR = Path(tempfile.mkdtemp(prefix="run-", dir=_TMP_ROOT))

os.environ["DATA_SOURCE"] = "mock"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(_RUN_DIR / 'test.db').as_posix()}"
os.environ["DEFAULT_MIN_MARGIN_PCT"] = "0"
# Воркер выключен: обходы запускаем явно, чтобы результат был детерминированным.
os.environ["ENABLE_INGESTION"] = "false"
os.environ["MAX_REQUESTS_PER_MINUTE"] = "600"

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402

DEMO = {"username": "demo", "password": "demo12345"}
OTHER = {"username": "student", "password": "student123"}


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001 - хук pytest
    """Убираем временные БД, чтобы не копить мусор между прогонами."""
    shutil.rmtree(_RUN_DIR, ignore_errors=True)


@pytest.fixture(scope="session")
def client():
    """Один клиент на сессию: lifespan (БД, seed, первый обход) выполняется один раз."""
    with TestClient(app) as test_client:
        yield test_client


def _token(client: TestClient, credentials: dict[str, str]) -> str:
    response = client.post("/api/auth/login", json=credentials)
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture(scope="session")
def token(client: TestClient) -> str:
    return _token(client, DEMO)


@pytest.fixture(scope="session")
def auth(token: str) -> dict[str, str]:
    """Заголовок авторизации демо-пользователя."""
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def other_auth(client: TestClient) -> dict[str, str]:
    """Заголовок второго пользователя — для проверки изоляции данных."""
    return {"Authorization": f"Bearer {_token(client, OTHER)}"}
