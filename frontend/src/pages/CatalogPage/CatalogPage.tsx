/**
 * Каталог предметов.
 *
 * Фильтры (поиск, группа, сортировка, страница) живут в Zustand-хранилище,
 * поэтому сохраняются при переходе в карточку предмета и обратно.
 * Каждый запрос проходит через единый паттерн loading/error/data.
 */

import { useMemo, type ChangeEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { catalogSorts, fetchCatalog, fetchCatalogGroups } from "@/api/endpoints";
import { AsyncView } from "@/components/AsyncView/AsyncView";
import { PageHeader } from "@/components/ui/ui";
import { useAsync } from "@/hooks/useAsync";
import { useCatalogFilterStore } from "@/store/catalogFilterStore";
import type { CatalogGroup, CatalogPage, CatalogSort } from "@/types/models";
import { formatMoney } from "@/utils/format";

import styles from "./CatalogPage.module.css";

interface CatalogData {
  page: CatalogPage;
  groups: CatalogGroup[];
}

export function CatalogPage(): ReactNode {
  const search = useCatalogFilterStore((state) => state.search);
  const group = useCatalogFilterStore((state) => state.group);
  const sort = useCatalogFilterStore((state) => state.sort);
  const page = useCatalogFilterStore((state) => state.page);
  const limit = useCatalogFilterStore((state) => state.limit);
  const setSearch = useCatalogFilterStore((state) => state.setSearch);
  const setGroup = useCatalogFilterStore((state) => state.setGroup);
  const setSort = useCatalogFilterStore((state) => state.setSort);
  const setPage = useCatalogFilterStore((state) => state.setPage);
  const reset = useCatalogFilterStore((state) => state.reset);

  // Стабильный ключ зависимостей: запрос уходит только при смене фильтров.
  const queryKey = useMemo(
    () => JSON.stringify({ search, group, sort, page, limit }),
    [search, group, sort, page, limit],
  );

  const { state, reload } = useAsync<CatalogData>(async () => {
    const [pageData, groups] = await Promise.all([
      fetchCatalog({ search, group, sort, offset: page * limit, limit }),
      fetchCatalogGroups(),
    ]);
    return { page: pageData, groups };
  }, [queryKey]);

  const totalPages = state.status === "success" ? Math.ceil(state.data.page.total / limit) : 0;

  return (
    <>
      <PageHeader
        eyebrow="Каталог"
        title="Предметы аукциона"
        subtitle="Полный ассортимент с ценами и группировкой. Отсюда можно посчитать выгоду по конкретной позиции."
      />

      <div className={styles.toolbar}>
        <label className={styles.searchField}>
          <span className={styles.searchIcon} aria-hidden="true">
            ⌕
          </span>
          <input
            className={styles.search}
            placeholder="Поиск по названию или id"
            value={search}
            onChange={(event: ChangeEvent<HTMLInputElement>) => setSearch(event.target.value)}
          />
        </label>

        <label className={styles.selectField}>
          <span className={styles.selectLabel}>Группа</span>
          <select
            className={styles.select}
            value={group}
            onChange={(event) => setGroup(event.target.value)}
          >
            <option value="">Все группы</option>
            {(state.status === "success" ? state.data.groups : []).map((entry) => (
              <option key={entry.group} value={entry.group}>
                {entry.group} ({entry.count})
              </option>
            ))}
          </select>
        </label>

        <label className={styles.selectField}>
          <span className={styles.selectLabel}>Сортировка</span>
          <select
            className={styles.select}
            value={sort}
            onChange={(event) => setSort(event.target.value as CatalogSort)}
          >
            {catalogSorts.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <button type="button" className={styles.reset} onClick={reset}>
          Сбросить
        </button>
      </div>

      <AsyncView
        state={state}
        onRetry={reload}
        loadingText="Читаю каталог…"
        isEmpty={(data) => data.page.items.length === 0}
        emptyText="Ничего не найдено"
        emptyHint="Попробуйте изменить запрос или сбросить фильтры."
      >
        {({ page: pageData }) => (
          <>
            <div className={styles.summary}>
              <span>
                Найдено <b className="num">{formatMoney(pageData.total)}</b> из{" "}
                <b className="num">{formatMoney(pageData.catalog_total)}</b>
              </span>
              <span>
                Страница {page + 1} из {Math.max(totalPages, 1)}
              </span>
            </div>

            <div className={styles.list}>
              {pageData.items.map((item) => (
                <Link key={item.id} to={`/catalog/${item.id}`} className={styles.row}>
                  <div className={styles.rowMain}>
                    <span className={styles.rowTitle}>{item.title}</span>
                    <span className={styles.rowMeta}>
                      {item.group}
                      {item.subgroup ? ` · ${item.subgroup}` : ""}
                      {item.tier_label ? ` · ${item.tier_label}` : ""}
                    </span>
                  </div>

                  <div className={styles.rowPrice}>
                    <span className={`${styles.price} num`}>{formatMoney(item.base_price)} ₽</span>
                    <span className={styles.priceHint}>
                      {item.estimated ? "оценка по группе" : "средняя по рынку"}
                    </span>
                  </div>

                  <span className={styles.chevron} aria-hidden="true">
                    →
                  </span>
                </Link>
              ))}
            </div>

            <div className={styles.pager}>
              <button
                type="button"
                className={styles.pagerButton}
                disabled={page === 0}
                onClick={() => setPage(page - 1)}
              >
                ← Назад
              </button>
              <span className={styles.pagerInfo}>
                {page * limit + 1}–{Math.min((page + 1) * limit, pageData.total)} из {pageData.total}
              </span>
              <button
                type="button"
                className={styles.pagerButton}
                disabled={page + 1 >= totalPages}
                onClick={() => setPage(page + 1)}
              >
                Вперёд →
              </button>
            </div>
          </>
        )}
      </AsyncView>
    </>
  );
}
