"""Тесты каталога предметов: названия, группы, иконки."""

from __future__ import annotations

from services.catalog import get_catalog


def test_catalog_is_loaded_from_official_database() -> None:
    catalog = get_catalog()
    assert len(catalog) > 20, "каталог должен содержать предметы из официальной базы"
    item = catalog.all()[0]
    assert item.id
    assert item.title and item.title != item.id
    assert "/" in item.category
    assert item.group


def test_catalog_groups_sorted_and_counted() -> None:
    groups = get_catalog().groups()
    assert groups
    names = [row["group"] for row in groups]
    assert names == sorted(names)
    assert sum(row["count"] for row in groups) == len(get_catalog())


def test_catalog_describe_unknown_item_is_safe() -> None:
    catalog = get_catalog()
    known = catalog.all()[0]
    assert catalog.describe(known.id)["title"] == known.title

    unknown = catalog.describe("zzzzz")
    assert unknown["title"].startswith("Неизвестный предмет")
    assert unknown["category"] == "unknown"


def test_catalog_search_by_title_and_id() -> None:
    catalog = get_catalog()
    item = catalog.all()[0]
    assert item in catalog.search(item.title[:6])
    assert item in catalog.search(item.id)
    assert catalog.search("название-которого-нет-в-базе") == []
