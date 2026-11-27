/**
 * Обзор рынка: лента самых выгодных лотов + сводка по каталогу.
 */

import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { fetchCatalog, fetchDeals } from "@/api/endpoints";
import { AsyncView } from "@/components/AsyncView/AsyncView";
import { PageHeader, StatCard, VerdictBadge } from "@/components/ui/ui";
import { useAsync } from "@/hooks/useAsync";
import type { CatalogPage, Deal } from "@/types/models";
import { formatMoney, formatPercent } from "@/utils/format";

import styles from "./DashboardPage.module.css";

interface Overview {
  deals: Deal[];
  catalog: CatalogPage;
}

async function loadOverview(): Promise<Overview> {
  const [deals, catalog] = await Promise.all([fetchDeals(24, 0), fetchCatalog({ limit: 1 })]);
  return { deals, catalog };
}

export function DashboardPage(): ReactNode {
  const { state, reload } = useAsync<Overview>(loadOverview, []);

  return (
    <>
      <PageHeader
        eyebrow="Рынок"
        title="Что выгодно прямо сейчас"
        subtitle="Лоты аукциона, отсортированные по марже после комиссии. Цель продажи — 75-й перцентиль цен проданных лотов."
        actions={
          <Link to="/calculator" className={styles.cta}>
            Посчитать выгоду
          </Link>
        }
      />

      <AsyncView
        state={state}
        onRetry={reload}
        loadingText="Собираю лоты и цены…"
        isEmpty={(data) => data.deals.length === 0}
        emptyText="Подходящих лотов нет"
        emptyHint="Индекс рынка не содержит лотов с положительной маржой — попробуйте позже."
      >
        {({ deals, catalog }) => (
          <>
            <div className={styles.stats}>
              <StatCard
                label="Предметов в каталоге"
                value={formatMoney(catalog.catalog_total)}
                hint="полный ассортимент аукциона"
              />
              <StatCard
                label="В мониторинге"
                value={formatMoney(catalog.tracked_total)}
                hint="обход воркером"
              />
              <StatCard
                label="Лотов в ленте"
                value={String(deals.length)}
                hint="с неотрицательной маржой"
              />
              <StatCard
                label="Лучшая маржа"
                value={formatPercent(deals[0]?.quote.margin_pct ?? 0)}
                tone="positive"
                hint={deals[0]?.title ?? "—"}
              />
            </div>

            <div className={styles.grid}>
              {deals.map((deal) => (
                <Link
                  key={`${deal.item_id}-${deal.quality}-${deal.level}-${deal.quote.buy_price}`}
                  to={`/catalog/${deal.item_id}`}
                  className={styles.card}
                >
                  <div className={styles.cardTop}>
                    <span className={styles.cardTitle} title={deal.title}>
                      {deal.title}
                    </span>
                    <VerdictBadge verdict={deal.quote.verdict} />
                  </div>

                  <div className={styles.tags}>
                    <span className={styles.tag}>{deal.group}</span>
                    {deal.quality_label && <span className={styles.tag}>{deal.quality_label}</span>}
                    {deal.level > 0 && <span className={styles.tag}>+{deal.level}</span>}
                  </div>

                  <div className={styles.prices}>
                    <div>
                      <span className={styles.priceLabel}>Купить</span>
                      <span className={`${styles.price} num`}>{formatMoney(deal.quote.buy_price)} ₽</span>
                    </div>
                    <div>
                      <span className={styles.priceLabel}>Продать</span>
                      <span className={`${styles.price} num`}>{formatMoney(deal.quote.net_sell)} ₽</span>
                    </div>
                    <div>
                      <span className={styles.priceLabel}>Маржа</span>
                      <span className={`${styles.margin} num`}>
                        {formatPercent(deal.quote.margin_pct)}
                      </span>
                    </div>
                  </div>

                  <div className={styles.foot}>
                    <span>лоты: {deal.quote.lots_count}</span>
                    <span>конкуренты: {deal.quote.competition}</span>
                    <span>спрос: {deal.quote.sales_per_day.toFixed(1)}/сут</span>
                  </div>
                </Link>
              ))}
            </div>
          </>
        )}
      </AsyncView>
    </>
  );
}
