"""Ingestion: фоновый обход watchlist и вычисление сигналов.

Воркер живёт вне обработчиков запросов: он забирает лоты и историю из источника,
считает котировки, пишет снимки в БД, публикует события в SSE-шину и рассылает
личные (targeted) уведомления через WebSocket. Роутеры при этом читают только
БД и память — поэтому падение внешнего API не роняет сервис.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from config import Settings
from models.database import SessionLocal
from models.entities import Alert, FilterRule, PriceSnapshot, WatchItem, as_utc, utcnow
from services.catalog import get_catalog
from services.connections import ConnectionManager
from services.events import EventBus
from services.pricing import Quote, build_quote, matches_filter, normalize_lots, quality_label

logger = logging.getLogger(__name__)

ALERT_COOLDOWN_MINUTES = 15


@dataclass
class ScanStats:
    scanned: int = 0
    deals: int = 0
    alerts: int = 0
    errors: int = 0
    duration_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "deals": self.deals,
            "alerts": self.alerts,
            "errors": self.errors,
            "duration_ms": round(self.duration_ms, 1),
        }


class IngestionService:
    def __init__(
        self,
        settings: Settings,
        source: Any,
        bus: EventBus,
        manager: ConnectionManager,
    ) -> None:
        self._settings = settings
        self._source = source
        self._bus = bus
        self._manager = manager
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._scan_lock = asyncio.Lock()

        self.last_scan_at: datetime | None = None
        self.last_stats: ScanStats | None = None
        self.scans_total = 0
        # Актуальная картина рынка в памяти: item_id -> payload для API/SSE.
        self.latest: dict[str, dict[str, Any]] = {}
        self.quotes: dict[str, Quote] = {}
        # Последние лоты по предмету — для экрана карточки без запроса к API.
        self.lots: dict[str, list[dict[str, Any]]] = {}
        # История продаж меняется медленно: кэшируем и обновляем раз в N секунд.
        self._history_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        # Когда предмет обходили в последний раз — чтобы идти по кругу.
        self._last_touched: dict[str, float] = {}

    # ---------- жизненный цикл ----------

    @property
    def source(self) -> Any:
        """Источник данных (mock или клиент официального API)."""
        return self._source

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="ingestion-worker")
        logger.info("Ingestion-воркер запущен (интервал %s c)", self._settings.scan_interval_seconds)

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        close = getattr(self._source, "close", None)
        if close is not None:
            await close()
        logger.info("Ingestion-воркер остановлен")

    async def _run(self) -> None:
        # Первый обход — сразу при старте, чтобы интерфейс не был пустым.
        while not self._stop.is_set():
            try:
                await self.scan_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # воркер не должен умирать из-за одной ошибки
                logger.exception("Ошибка обхода аукциона")
            delay = max(5, self._settings.scan_interval_seconds)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                continue

    # ---------- обход ----------

    async def scan_once(self) -> ScanStats:
        async with self._scan_lock:
            started = time.perf_counter()
            stats = ScanStats()

            async with SessionLocal() as session:
                items = (
                    (await session.execute(select(WatchItem).where(WatchItem.enabled.is_(True)).order_by(WatchItem.priority)))
                    .scalars()
                    .all()
                )
                filters = (
                    (await session.execute(select(FilterRule).where(FilterRule.enabled.is_(True))))
                    .scalars()
                    .all()
                )

                # В мониторинге может быть больше предметов, чем успевает обойти
                # лимит API. Идём по кругу: сначала те, что дольше всех ждут.
                batch = sorted(items, key=lambda row: self._last_touched.get(row.item_id, 0.0))
                batch = batch[: max(1, self._settings.max_items_per_scan)]

                for item in batch:
                    stats.scanned += 1
                    try:
                        payloads = await self._scan_item(session, item)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        stats.errors += 1
                        logger.warning("Не удалось обновить «%s» (%s): %s", item.title or item.item_id, item.item_id, exc)
                        continue
                    finally:
                        self._last_touched[item.item_id] = time.monotonic()

                    for payload in payloads:
                        if payload["quote"]["margin_pct"] >= self._settings.default_min_margin_pct:
                            stats.deals += 1
                        await self._publish_deal(payload)
                        stats.alerts += await self._fire_alerts(session, item, payload, filters)

                await session.commit()

            stats.duration_ms = (time.perf_counter() - started) * 1000
            self.last_scan_at = utcnow()
            self.last_stats = stats
            self.scans_total += 1

            summary = {
                "type": "scan",
                "data": {
                    **stats.as_dict(),
                    "scans_total": self.scans_total,
                    "at": self.last_scan_at.isoformat(),
                    "source": self._settings.data_source,
                },
            }
            await self._bus.publish("scan", summary["data"])
            await self._manager.broadcast(summary)
            logger.info(
                "Обход завершён: предметов=%s, сигналов=%s, алертов=%s, ошибок=%s, %.0f мс",
                stats.scanned,
                stats.deals,
                stats.alerts,
                stats.errors,
                stats.duration_ms,
            )
            return stats

    @staticmethod
    def _band_of(level: int) -> int:
        """Диапазон прокачки: 0–5 / 5–10 / 10–15 (см. LEVEL_BANDS на фронтенде)."""
        return 0 if level <= 5 else 1 if level <= 10 else 2

    async def _scan_item(self, session: Any, item: WatchItem) -> list[dict[str, Any]]:
        lots = await self._source.fetch_lots(item.item_id, self._settings.lots_limit)
        history = await self._fetch_history(item.item_id)

        # У артефактов качество и прокачка — свойства конкретного лота.
        # Поэтому считаем котировку по группам «качество × диапазон прокачки»
        # и отдаём отдельную строку на каждую группу.
        is_artifact = item.category.startswith("artefact/")
        groups: dict[tuple[int, int], list[dict[str, Any]]] = {}
        if is_artifact:
            for lot in lots:
                level = int(lot.get("level") or 0)
                band = self._band_of(level)
                groups.setdefault((int(lot.get("quality") or 0), band), []).append(lot)
        else:
            groups[(0, 0)] = lots

        payloads: list[dict[str, Any]] = []
        best_quote = None
        for (quality, band), group_lots in sorted(groups.items()):
            # Для артефактов сравниваем цены выкупа и продажи внутри того же
            # класса (качество + диапазон прокачки), иначе получается «средняя
            # температура по больнице»: дешёвый обычный лот против легендарных продаж.
            group_history = history
            if is_artifact:
                same_class = [
                    lot
                    for lot in history
                    if int(lot.get("quality") or 0) == quality
                    and self._band_of(int(lot.get("level") or 0)) == band
                ]
                if same_class:
                    group_history = same_class

            quote = build_quote(
                group_lots,
                group_history,
                fee_pct=self._settings.fee_pct,
                competition_tolerance=self._settings.competition_tolerance,
                window_days=self._settings.history_window_days,
                min_margin_pct=self._settings.default_min_margin_pct,
            )
            if quote is None:
                continue
            if best_quote is None or quote.margin_pct > best_quote.margin_pct:
                best_quote = quote
            payloads.append({"quote": quote, "band": band, "quality": quality})

        if not payloads or best_quote is None:
            return []

        # Название/категория могли не заполниться при добавлении предмета.
        if not item.title or item.title == item.item_id:
            describe = getattr(self._source, "describe", None)
            if describe is not None:
                info = describe(item.item_id) or {}
                item.title = info.get("title") or item.title
                item.category = item.category or info.get("category", "")

        now = utcnow()
        self.quotes[item.item_id] = best_quote
        normalized = normalize_lots(lots)[: self._settings.lots_limit]
        self.lots[item.item_id] = [
            {
                "lot_id": lot.lot_id,
                "amount": lot.amount,
                "total_price": round(lot.total_price, 2),
                "unit_price": round(lot.unit_price, 2),
            }
            for lot in normalized
        ]
        session.add(
            PriceSnapshot(
                item_id=item.item_id,
                ts=now,
                buy_price=best_quote.buy_price,
                sell_target=best_quote.sell_target,
                margin_pct=best_quote.margin_pct,
                median_price=best_quote.median_price,
                p75_price=best_quote.p75_price,
                p25_price=best_quote.p25_price,
                lots_count=best_quote.lots_count,
                competition=best_quote.competition,
                sales_per_day=best_quote.sales_per_day,
                liquidity_score=best_quote.liquidity_score,
                raw={"lots": len(lots), "history": len(history), "groups": len(payloads)},
            )
        )

        entry = get_catalog().get(item.item_id)
        result: list[dict[str, Any]] = []
        # чистим устаревшие группы этого предмета (например, ступень качества исчезла)
        for stale_key in self._keys_for(item.item_id):
            self.latest.pop(stale_key, None)

        for group in payloads:
            quote: Quote = group["quote"]
            band = int(group["band"])
            key = item.item_id if not is_artifact else f"{item.item_id}:{quote.quality}:{band}"
            payload = {
                "key": key,
                "item_id": item.item_id,
                "title": item.title or item.item_id,
                "category": item.category,
                "group": entry.group if entry else "Без категории",
                "icon_url": item.icon_url,
                "quality": quote.quality,
                "quality_label": quality_label(quote.quality),
                "level": quote.level,
                "level_band": band,
                "level_label": f"+{quote.level}" if quote.quality else "",
                "quote": quote.as_dict(),
                "updated_at": now.isoformat(),
                "stale_seconds": 0.0,
            }
            self.latest[key] = payload
            result.append(payload)
        return result

    def _keys_for(self, item_id: str) -> list[str]:
        prefix = item_id + ":"
        return [key for key in list(self.latest) if key == item_id or key.startswith(prefix)]

    def best_payload(self, item_id: str) -> dict[str, Any] | None:
        """Самая выгодная строка предмета (для карточки на фронтенде)."""
        payloads = [self.latest[key] for key in self._keys_for(item_id) if key in self.latest]
        if not payloads:
            return None
        return max(payloads, key=lambda row: row["quote"]["margin_pct"])

    async def _fetch_history(self, item_id: str) -> list[dict[str, Any]]:
        """История продаж с кэшем: экономим лимит запросов к API."""
        ttl = max(30, self._settings.history_refresh_seconds)
        cached = self._history_cache.get(item_id)
        now = time.monotonic()
        if cached is not None and now - cached[0] < ttl:
            return cached[1]
        history = await self._source.fetch_history(item_id, self._settings.history_limit)
        self._history_cache[item_id] = (now, history)
        return history

    async def _publish_deal(self, payload: dict[str, Any]) -> None:
        await self._bus.publish("deal", payload)
        # Общий broadcast: событие рынка видят все вкладки без перезагрузки.
        await self._manager.broadcast({"type": "deal", "data": payload})

    async def _fire_alerts(
        self,
        session: Any,
        item: WatchItem,
        payload: dict[str, Any],
        filters: list[FilterRule],
    ) -> int:
        """Личные уведомления: только владельцу сработавшего фильтра."""
        if not filters:
            return 0
        quote = self.quotes.get(item.item_id)
        if quote is None:
            return 0

        created = 0
        cooldown_from = utcnow() - timedelta(minutes=ALERT_COOLDOWN_MINUTES)
        for rule in filters:
            if not matches_filter(
                quote,
                item.item_id,
                item.category,
                min_margin_pct=rule.min_margin_pct,
                min_sales_per_day=rule.min_sales_per_day,
                max_competition=rule.max_competition,
                category_prefix=rule.category_prefix,
                item_ids=rule.item_ids or (),
            ):
                continue
            recent = await session.execute(
                select(Alert.id)
                .where(Alert.user_id == rule.user_id)
                .where(Alert.item_id == item.item_id)
                .where(Alert.filter_id == rule.id)
                .where(Alert.created_at >= cooldown_from)
                .limit(1)
            )
            if recent.first() is not None:
                continue

            alert = Alert(
                user_id=rule.user_id,
                filter_id=rule.id,
                item_id=item.item_id,
                title=item.title or item.item_id,
                margin_pct=quote.margin_pct,
                buy_price=quote.buy_price,
                sell_price=quote.sell_target,
            )
            session.add(alert)
            await session.flush()
            created += 1

            message = {
                "type": "alert",
                "data": {
                    "id": alert.id,
                    "filter_id": rule.id,
                    "filter_name": rule.name,
                    "item_id": item.item_id,
                    "title": alert.title,
                    "icon_url": item.icon_url,
                    "margin_pct": round(quote.margin_pct, 2),
                    "buy_price": round(quote.buy_price, 2),
                    "sell_price": round(quote.sell_target, 2),
                    "created_at": alert.created_at.isoformat() if alert.created_at else utcnow().isoformat(),
                },
            }
            delivered = await self._manager.send_to_room(rule.user_id, message)
            logger.info(
                "Алерт «%s» для %s (доставлено сокетов: %s)", alert.title, rule.user_id, delivered
            )
        return created

    # ---------- доступ к данным ----------

    def forget(self, item_id: str) -> None:
        """Чистит кэши предмета после удаления из мониторинга."""
        for key in self._keys_for(item_id):
            self.latest.pop(key, None)
        self.quotes.pop(item_id, None)
        self.lots.pop(item_id, None)
        self._history_cache.pop(item_id, None)

    def deal_payloads(self) -> list[dict[str, Any]]:
        """Текущие котировки с пересчитанной «свежестью»."""
        now = datetime.now(timezone.utc)
        result: list[dict[str, Any]] = []
        for payload in self.latest.values():
            copy = {**payload, "quote": dict(payload["quote"])}
            updated_at = payload.get("updated_at")
            if updated_at:
                try:
                    dt = as_utc(datetime.fromisoformat(updated_at))
                    copy["stale_seconds"] = round((now - dt).total_seconds(), 1) if dt else None
                except ValueError:
                    copy["stale_seconds"] = None
            result.append(copy)
        result.sort(key=lambda row: row["quote"]["margin_pct"], reverse=True)
        return result
