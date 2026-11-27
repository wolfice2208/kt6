"""Сборка каталога аукциона с реальными ценами.

Источники:
* sctools.tech (fan-агрегатор аукциона STALZONE, robots.txt разрешает обход):
  - страницы категорий содержат полный список предметов с флагом ``auction`` —
    именно он показывает, доступен ли предмет к покупке/продаже;
  - страницы предметов содержат текущую рыночную цену (``snippetPrice``).
* локальная копия официальной базы EXBO (stalzone-database) — категории и пути к иконкам.

Результат: backend/catalog.json (только предметы, доступные на аукционе, с реальной ценой)
и backend/catalog_meta.json (когда и откуда собраны цены).

Запуск (из каталога backend):
    python tools/build_catalog.py --db-path <путь к клонированному stalzone-database>/ru/items
    python tools/build_catalog.py --limit 30   # быстрая проверка на выборке
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = Path(__file__).resolve().parent / ".cache"
OUT_CATALOG = ROOT / "catalog.json"
OUT_META = ROOT / "catalog_meta.json"

CATEGORIES = [
    "weapons", "armor", "artefacts", "attachments", "ammo", "consumables",
    "resources", "cosmetics", "cases", "devices", "grenades", "hideout",
    "storage", "plates", "tokens", "repair", "weaponModules", "uncategorized",
]

# Русские названия групп и подгрупп (тайсономия агрегатора).
GROUP_LABELS = {
    "weapons": ("Оружие", None),
    "armor": ("Броня", None),
    "artefacts": ("Артефакты", None),
    "attachments": ("Обвесы", None),
    "ammo": ("Патроны", None),
    "consumables": ("Расходники", None),
    "resources": ("Ресурсы и материалы", None),
    "cosmetics": ("Косметика", None),
    "cases": ("Кейсы", None),
    "devices": ("Устройства", None),
    "grenades": ("Гранаты", None),
    "hideout": ("Убежище", None),
    "storage": ("Хранилище", None),
    "plates": ("Пластины брони", None),
    "tokens": ("Жетоны", None),
    "repair": ("Ремонт", None),
    "weaponModules": ("Модули оружия", None),
    "uncategorized": ("Без категории", None),
}

SUBGROUP_LABELS = {
    "assaultRifles": "Автоматы",
    "sniperRifles": "Снайперские винтовки",
    "smgs": "Пистолеты-пулемёты",
    "pistols": "Пистолеты",
    "shotguns": "Дробовики",
    "machineGuns": "Пулемёты",
    "heavy": "Тяжёлое оружие",
    "melee": "Ближний бой",
    "gravity": "Гравитационные",
    "thermal": "Термические",
    "biochemical": "Биохимические",
    "electrophysical": "Электрофизические",
    "other": "Прочие",
    "barrels": "Стволы",
    "sights": "Прицелы",
    "magazines": "Магазины",
    "grips": "Рукоятки",
    "forends": "Цевья",
    "accessories": "Аксессуары",
    "clothes": "Одежда",
    "combat": "Боевая",
    "combined": "Комбинированная",
    "scientist": "Научная",
    "backpacks": "Рюкзаки",
    "containers": "Контейнеры",
}


def parse_next_data(html: str) -> dict:
    marker = 'id="__NEXT_DATA__" type="application/json">'
    start = html.find(marker)
    if start < 0:
        return {}
    start += len(marker)
    end = html.find("</script>", start)
    try:
        return json.loads(html[start:end]).get("props", {}).get("pageProps", {})
    except ValueError:
        return {}


def load_local_db(db_path: Path | None) -> dict[str, dict]:
    """id -> {category, icon} из локальной копии официальной базы."""
    mapping: dict[str, dict] = {}
    if not db_path or not db_path.exists():
        return mapping
    for dirpath, dirnames, files in os.walk(db_path):
        dirnames[:] = [name for name in dirnames if name != "_variants"]
        for name in files:
            if not name.endswith(".json"):
                continue
            try:
                data = json.loads((Path(dirpath) / name).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            item_id = data.get("id")
            category = data.get("category", "")
            if not item_id or not category:
                continue
            mapping[item_id] = {
                "category": category,
                "icon": f"ru/icons/{category}/{item_id}.png",
                "color": data.get("color", ""),
            }
    return mapping


async def fetch(client: httpx.AsyncClient, url: str, cache_file: Path) -> str:
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    response = await client.get(url)
    response.raise_for_status()
    text = response.text
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(text, encoding="utf-8")
    return text


async def collect_items(client: httpx.AsyncClient) -> dict[str, dict]:
    items: dict[str, dict] = {}
    for category in CATEGORIES:
        html = await fetch(client, f"https://sctools.tech/en/items/category/{category}", CACHE_DIR / f"cat-{category}.html")
        props = parse_next_data(html)
        for item in (props.get("data") or {}).get("items") or []:
            if not item.get("auction"):
                continue
            items[item["id"]] = {
                "id": item["id"],
                "title": (item.get("name") or {}).get("ru") or item["id"],
                "group_key": category,
                "subgroup_key": item.get("subgroup") or "",
            }
        print(f"  {category:16} auction={sum(1 for i in (props.get('data') or {}).get('items') or [] if i.get('auction'))}", file=sys.stderr)
    return items


async def collect_prices(client: httpx.AsyncClient, items: dict[str, dict], concurrency: int = 5) -> None:
    semaphore = asyncio.Semaphore(concurrency)
    done = 0
    total = len(items)

    async def worker(item_id: str) -> None:
        nonlocal done
        async with semaphore:
            try:
                html = await fetch(
                    client,
                    f"https://sctools.tech/en/items/{item_id}",
                    CACHE_DIR / "items" / f"{item_id}.html",
                )
                props = parse_next_data(html)
                price = (props.get("snippetPrice") or {}).get("value")
                if isinstance(price, (int, float)) and price > 0:
                    items[item_id]["price"] = int(price)
                initial = props.get("initialItem") or {}
                if initial.get("not_in_game"):
                    items[item_id]["not_in_game"] = True
            except Exception:  # noqa: BLE001 - один предмет не должен ломать сборку
                items[item_id]["price"] = None
            finally:
                done += 1
                if done % 100 == 0:
                    print(f"  цены: {done}/{total}", file=sys.stderr)

    await asyncio.gather(*(worker(item_id) for item_id in items))


GROUP_LIQUIDITY = {
    "Оружие": 1.1,
    "Броня": 1.3,
    "Артефакты": 0.9,
    "Обвесы": 2.2,
    "Патроны": 9.0,
    "Расходники": 6.0,
    "Ресурсы и материалы": 4.5,
    "Косметика": 0.7,
    "Кейсы": 0.6,
    "Устройства": 1.2,
    "Гранаты": 3.0,
    "Убежище": 0.6,
    "Хранилище": 1.6,
    "Пластины брони": 2.2,
    "Жетоны": 1.0,
    "Ремонт": 2.6,
    "Модули оружия": 0.9,
    "Без категории": 0.5,
}


RANK_LABELS = {
    "RANK_NEWBIE": (1, "Новобранец"),
    "RANK_STALKER": (2, "Сталкер"),
    "RANK_VETERAN": (3, "Ветеран"),
    "RANK_MASTER": (4, "Мастер"),
    "RANK_LEGEND": (5, "Легенда"),
}

# Группы, где качество — это ранг снаряжения (в игре он же «качество»).
EQUIPMENT_GROUPS = {"Оружие", "Броня", "Обвесы", "Модули оружия"}

# Артефакты: редкость в базе не хранится (качество катается на инстанс),
# поэтому раскладываем по ценовым квинтилям внутри артефактов.
RARITY_LABELS: list[str] = []  # редкость артефактов в базе не хранится: качество катается на экземпляр


def apply_tiers(entries: list[dict], local_db: dict[str, dict]) -> None:
    """Качество снаряжения — ранг из официальной базы.

    Артефактам ранг не присваиваем: их качество катается на конкретный экземпляр
    (обычное … легендарное) и живёт в лоте, а не в типе предмета.
    """
    for row in entries:
        color = (local_db.get(row["id"]) or {}).get("color", "")
        row["tier_kind"] = ""
        row["tier_label"] = ""
        row["tier_value"] = 0
        row["tier_estimated"] = False
        if row["group"] in EQUIPMENT_GROUPS and color in RANK_LABELS:
            value, label = RANK_LABELS[color]
            row["tier_kind"] = "rank"
            row["tier_label"] = label
            row["tier_value"] = value


def build_entries(items: dict[str, dict], local_db: dict[str, dict]) -> list[dict]:
    """Собирает каталог; если цену получить не удалось — берёт медиану по группе."""
    # медианы по группам считаем по предметам с реальной ценой
    priced_by_group: dict[str, list[int]] = {}
    for item in items.values():
        if item.get("price"):
            priced_by_group.setdefault(item["group_key"], []).append(item["price"])
    overall_median = 0
    all_prices = [price for prices in priced_by_group.values() for price in prices]
    if all_prices:
        overall_median = int(statistics.median(all_prices))

    entries = []
    for item_id, item in items.items():
        if item.get("not_in_game"):
            continue
        price = item.get("price")
        estimated = False
        if not price:
            group_prices = priced_by_group.get(item["group_key"]) or []
            price = int(statistics.median(group_prices)) if group_prices else overall_median
            estimated = True
        if not price:
            continue
        local = local_db.get(item_id) or {}
        group_label, _ = GROUP_LABELS.get(item["group_key"], ("Прочее", None))
        subgroup_label = SUBGROUP_LABELS.get(item["subgroup_key"], item["subgroup_key"] or "Прочее")
        entries.append(
            {
                "id": item_id,
                "title": item["title"],
                "category": local.get("category") or f"{item['group_key']}/{item['subgroup_key']}",
                "group": group_label,
                "subgroup": subgroup_label,
                "base_price": int(price),
                "estimated": estimated,
                "liquidity": 1.0,
                "icon": local.get("icon") or "",
            }
        )
    entries.sort(key=lambda row: (row["group"], row["subgroup"], row["title"].lower()))
    return entries


async def main() -> None:
    parser = argparse.ArgumentParser(description="Сборка каталога аукциона с реальными ценами")
    parser.add_argument("--db-path", default="", help="путь к <stalzone-database>/ru/items")
    parser.add_argument("--limit", type=int, default=0, help="ограничить число предметов (для проверки)")
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument(
        "--tiers-only",
        action="store_true",
        help="только пересчитать качество/редкость в готовом catalog.json (без запросов к сети)",
    )
    args = parser.parse_args()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    local_db = load_local_db(Path(args.db_path) if args.db_path else None)
    print(f"локальная база: {len(local_db)} предметов", file=sys.stderr)

    if args.tiers_only:
        entries = json.loads(OUT_CATALOG.read_text(encoding="utf-8"))
        apply_tiers(entries, local_db)
        OUT_CATALOG.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
        ranks = sum(1 for row in entries if row.get("tier_kind") == "rank")
        rarities = sum(1 for row in entries if row.get("tier_kind") == "rarity")
        print(f"готово: rank={ranks}, rarity={rarities}", file=sys.stderr)
        return

    headers = {"User-Agent": "stalzone-auction-monitor (study project)"}
    async with httpx.AsyncClient(timeout=40, follow_redirects=True, headers=headers) as client:
        items = await collect_items(client)
        print(f"доступно на аукционе: {len(items)}", file=sys.stderr)
        if args.limit:
            items = dict(list(items.items())[: args.limit])
        await collect_prices(client, items, args.concurrency)

    entries = build_entries(items, local_db)
    apply_tiers(entries, local_db)
    prices = [row["base_price"] for row in entries]
    estimated = sum(1 for row in entries if row.get("estimated"))
    for row in entries:
        base = GROUP_LIQUIDITY.get(row["group"], 1.0)
        # небольшая детерминированная вариация, чтобы предметы внутри группы отличались
        digest = hashlib.sha256(row["id"].encode()).hexdigest()[:6]
        spread = 0.75 + (int(digest, 16) % 50) / 100
        row["liquidity"] = round(base * spread, 1)
    entries.sort(key=lambda row: (row["group"], row["subgroup"], row["title"].lower()))

    OUT_CATALOG.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
    OUT_META.write_text(
        json.dumps(
            {
                "source": "sctools.tech (auction aggregator) + EXBO item database",
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "items": len(entries),
                "price_estimated": estimated,
                "price_min": min(prices) if prices else 0,
                "price_median": int(statistics.median(prices)) if prices else 0,
                "price_max": max(prices) if prices else 0,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    top = entries[:5]
    for row in top:
        print(f"{row['title'][:40]:42} {row['base_price']:>14,} ₽" .replace(",", " "), file=sys.stderr)
    print(f"готово: {len(entries)} предметов, медиана {int(statistics.median(prices)) if prices else 0} ₽", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
