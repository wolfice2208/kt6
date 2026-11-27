"""Роутер: лента выгодных лотов и сводная статистика рынка."""

from __future__ import annotations

import statistics

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from deps import IngestionDep, SessionDep
from models.entities import WatchItem

router = APIRouter(prefix="/deals", tags=["deals"])


@router.get("")
async def list_deals(
    ingestion: IngestionDep,
    min_margin_pct: float | None = Query(None, description="Нижняя граница маржи; без параметра — все лоты, включая убыточные"),
    verdict: str | None = Query(None, pattern="^(buy|watch|skip)$"),
    category: str | None = None,
    quality: int | None = Query(None, ge=1, le=7, description="Качество артефакта (1–7)"),
    level_min: int | None = Query(None, ge=0, le=15, description="Прокачка: нижняя граница"),
    level_max: int | None = Query(None, ge=0, le=15, description="Прокачка: верхняя граница"),
    limit: int = Query(1000, ge=1, le=2000),
) -> list[dict]:
    deals = ingestion.deal_payloads()
    result = []
    for deal in deals:
        quote = deal["quote"]
        if min_margin_pct is not None and quote["margin_pct"] < min_margin_pct:
            continue
        if verdict and quote["verdict"] != verdict:
            continue
        if category and not deal["category"].lower().startswith(category.lower()):
            continue
        if quality is not None and deal.get("quality") != quality:
            continue
        level = int(deal.get("level") or 0)
        if level_min is not None and level < level_min:
            continue
        if level_max is not None and level > level_max:
            continue
        result.append(deal)
    return result[:limit]


@router.get("/stats")
async def deals_stats(ingestion: IngestionDep, session: SessionDep) -> dict:
    deals = ingestion.deal_payloads()
    quotes = [deal["quote"] for deal in deals]
    margins = [quote["margin_pct"] for quote in quotes]
    buy = [quote for quote in quotes if quote["verdict"] == "buy"]
    tracked = int((await session.execute(select(func.count()).select_from(WatchItem))).scalar_one())
    profitable = sum(1 for margin in margins if margin > 0)
    return {
        "items_tracked": tracked,
        "items_with_data": len({deal["item_id"] for deal in deals}),
        "rows_total": len(deals),
        "profitable_rows": profitable,
        "unprofitable_rows": len(deals) - profitable,
        "deals_total": len(buy),
        "avg_margin_pct": round(sum(margins) / len(margins), 2) if margins else 0.0,
        "median_margin_pct": round(statistics.median(margins), 2) if margins else 0.0,
        "best_margin_pct": round(max(margins), 2) if margins else 0.0,
        "worst_margin_pct": round(min(margins), 2) if margins else 0.0,
        "last_scan_at": ingestion.last_scan_at.isoformat() if ingestion.last_scan_at else None,
        "scan_stats": ingestion.last_stats.as_dict() if ingestion.last_stats else None,
    }
