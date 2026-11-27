"""Конфигурация приложения.

Все значения читаются из переменных окружения / файла .env (pydantic-settings).
CORS-источники задаются строкой через запятую, чтобы их можно было менять
без правки кода.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Приложение ---
    app_name: str = "Протокол"
    app_version: str = "2.0.0"
    # User-Agent должен быть ASCII: HTTP-заголовки не умеют кириллицу.
    user_agent: str = "Protokol/2.0 (stalzone-auction-monitor)"
    debug: bool = False
    api_prefix: str = "/api"

    # --- Источник данных: mock | demo | live ---
    # mock — синтетические данные, работает без сети (страховка на защите);
    # demo — официальный demo API STALZONE (dapi), публичные токены из документации;
    # live — production API (eapi) с токеном, выданным EXBO после регистрации приложения.
    data_source: Literal["mock", "demo", "live"] = "mock"

    stalzone_api_base: str = "https://eapi.stalcraft.net"
    stalzone_demo_base: str = "https://dapi.stalzone.com"
    stalzone_region: str = "RU"
    stalzone_app_token: str = ""
    stalzone_client_id: str = ""
    stalzone_client_secret: str = ""
    stalzone_scope: str = ""
    stalzone_token_url: str = ""
    stalzone_timeout_seconds: float = 15.0

    # --- Сеть / CORS ---
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- База данных ---
    database_url: str = ""
    data_dir: Path = BASE_DIR / "data"

    # --- Аутентификация (JWT) ---
    # В учебном проекте секрет по умолчанию лежит в .env; на проде он
    # обязательно переопределяется и не коммитится.
    jwt_secret: str = "protokol-local-development-secret-do-not-use-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 240
    # Демо-данные создаются один раз при пустой БД.
    seed_demo_users: bool = True
    seed_demo_trades: bool = True

    # --- Каталог предметов ---
    catalog_file: Path = BASE_DIR / "catalog.json"
    catalog_meta_file: Path = BASE_DIR / "catalog_meta.json"
    icon_base_url: str = "https://raw.githubusercontent.com/EXBO-Studio/stalzone-database/main"
    catalog_lookup_limit: int = 300
    seed_items_limit: int = 120

    # --- Экономика аукциона ---
    fee_pct: float = 0.05
    default_min_margin_pct: float = 15.0
    history_window_days: int = 7
    history_limit: int = 200
    lots_limit: int = 50
    competition_tolerance: float = 0.05

    # --- Ingestion ---
    enable_ingestion: bool = True
    scan_interval_seconds: int = 45
    max_requests_per_minute: int = 180
    http_retries: int = 3
    history_refresh_seconds: int = 180
    max_items_per_scan: int = 120

    @field_validator("fee_pct")
    @classmethod
    def _check_fee(cls, value: float) -> float:
        if not 0 <= value < 1:
            raise ValueError("fee_pct должен быть в диапазоне [0, 1)")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite+aiosqlite:///{(self.data_dir / 'app.db').as_posix()}"

    @property
    def resolved_api_base(self) -> str:
        return self.stalzone_demo_base if self.data_source == "demo" else self.stalzone_api_base

    @property
    def resolved_token_url(self) -> str:
        if self.stalzone_token_url:
            return self.stalzone_token_url
        return f"{self.resolved_api_base.rstrip('/')}/oauth/token"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
