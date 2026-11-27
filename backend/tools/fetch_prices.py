"""Актуализация цен каталога по реальному API аукциона.

Источник: https://auction.sctools.tech/api/items/{id} (robots не запрещает).
Отдаёт статистику по предмету: ``averages`` — средние цены по качеству (0–6)
и диапазону прокачки (0-4 / 5-9 / 10-14 / 15), плюс ``lots_per_hour``.

Скрипт обновляет backend/catalog.json:
    prices          — матрица {качество: {диапазон: {price, lots_month}}}
    base_price      — взвешенная медиана реальных цен (для витрины и mock)
    lots_per_day    — оценка ликвидности из числа лотов за месяц
    price_updated_at

Запуск (из каталога backend):
    python tools/fetch_prices.py
    python tools/fetch_prices.py --limit 50     # проверка на выборке
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "auction-api"
CATALOG = ROOT / "catalog.json"
META = ROOT / "catalog_meta.json"
API = "https://auction.sctools.tech/api/items"
BANDS = ["0-4", "5-9", "10-14", "15"]


def parse_stats(payload: dict) -> dict:
    """Достаёт матрицу цен по качеству/диапазону прокачки."""
    averages = payload.get("averages") or {}
    prices: dict[str, dict[str, dict]] = {}
    for quality, bands in averages.items():
        if not isinstance(bands, dict):
            continue
        for band, cell in bands.items():
            if band not in BANDS or not isinstance(cell, dict):
                continue
            price = cell.get("avg_price")
            if not isinstance(price, (int, float)) or price <= 0:
                continue
            prices.setdefault(str(quality), {})[band] = {
                "price": float(price),
                "lots_month": int(cell.get("lots_month") or 0),
            }
    return prices


def weighted_median(prices: dict[str, dict[str, dict]]) -> float | None:
    """Медиана реальных цен с весом по числу лотов за месяц."""
    samples: list[float] = []
    for bands in prices.values():
        for cell in bands.values():
            weight = max(1, min(200, cell["lots_month"] // 10 or 1))
            samples.extend([cell["price"]] * weight)
    if not samples:
        return None
    return statistics.median(samples)


async def fetch_item(client: httpx.AsyncClient, item_id: str, semaphore: asyncio.Semaphore) -> dict | None:
    cache_file = CACHE_DIR / f"{item_id}.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    async with semaphore:
        for attempt in range(3):
            try:
                response = await client.get(f"{API}/{item_id}")
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                payload = response.json()
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                return payload
            except Exception:  # noqa: BLE001
                await asyncio.sleep(0.4 * (attempt + 1))
    return None


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    if args.limit:
        catalog = catalog[: args.limit]
    print(f"предметов: {len(catalog)}", file=sys.stderr)
    semaphore = asyncio.Semaphore(args.concurrency)
    headers = {"User-Agent": "Protokol/1.1 (stalzone-auction-monitor)"}
    async with httpx.AsyncClient(timeout=25, headers=headers, follow_redirects=True) as client:
        payloads = await asyncio.gather(*(fetch_item(client, row["id"], semaphore) for row in catalog))

    total = 0
    with_prices = 0
    for row, payload in zip(catalog, payloads):
        if not payload or "item_id" not in payload:
            continue
        total += 1
        prices = parse_stats(payload)
        medians = payload.get("medians") or {}
        recent_lots = payload.get("recent_lots") or []
        recent_unit = [lot.get("unit_price") for lot in recent_lots if isinstance(lot, dict) and lot.get("unit_price")]

        if prices:
            with_prices += 1
            median = weighted_median(prices)
            lots_month = sum(cell["lots_month"] for bands in prices.values() for cell in bands.values())
            row["prices"] = prices
            row["price_updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            row["lots_per_day"] = round(lots_month / 30, 2)
            if median:
                row["base_price"] = int(median)
            row["price_min"] = int(min(cell["price"] for bands in prices.values() for cell in bands.values()))
        else:
            # Не артефакт: статистика лежит в medians по периодам.
            period = medians.get("week") or medians.get("day") or medians.get("month") or {}
            price = period.get("avg_price")
            lots = period.get("lots") or 0
            if not isinstance(price, (int, float)) or price <= 0:
                continue
            with_prices += 1
            row["base_price"] = int(price)
            row["price_updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            row["price_min"] = int(min(recent_unit)) if recent_unit else int(price)
            row["lots_per_day"] = round(lots / 7, 2) if lots else round((payload.get("lots_per_hour") or 0) * 24, 2)
            row["medians"] = {
                key: {"price": int(value["avg_price"]), "lots": int(value.get("lots") or 0)}
                for key, value in medians.items()
                if isinstance(value, dict) and isinstance(value.get("avg_price"), (int, float))
            }
        row["estimated"] = False
        row["lots_per_hour"] = round(float(payload.get("lots_per_hour") or 0), 2)

    if args.limit:
        # Проверочный режим: только печатаем, каталог не перезаписываем.
        for row in catalog:
            prices = row.get("prices") or {}
            print(f"{row['id']}: качеств {len(prices)}, base {row.get('base_price')}", file=sys.stderr)
        return

    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")

    meta_path = META
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
    meta.update(
        {
            "source": "auction.sctools.tech API (реальные цены) + EXBO item database",
            "prices_fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "items": len(catalog),
            "items_with_prices": with_prices,
        }
    )
    prices_all = sorted(row["base_price"] for row in catalog if row.get("base_price"))
    if prices_all:
        meta["price_min"] = int(prices_all[0])
        meta["price_median"] = int(statistics.median(prices_all))
        meta["price_max"] = int(prices_all[-1])
        meta["prices_above_1m"] = sum(1 for price in prices_all if price >= 1_000_000)
        meta["prices_above_100m"] = sum(1 for price in prices_all if price >= 100_000_000)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    print(
        f"готово: ответов {total}, с ценами {with_prices}; "
        f"медиана {meta.get('price_median')}, максимум {meta.get('price_max')}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    asyncio.run(main())
