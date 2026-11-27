/**
 * Журнал сделок — защищённый маршрут /trades.
 *
 * Показывает сводку (выгода, ROI, винрейт), динамику по месяцам, топ предметов
 * и таблицу сделок. Данные личные: без токена страница недоступна, а бэкенд
 * вернул бы 401.
 */

import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { deleteTrade, fetchTrades, fetchTradesStats } from "@/api/endpoints";
import { AsyncView } from "@/components/AsyncView/AsyncView";
import { Badge, MonthBars, PageHeader, ProfitValue, StatCard } from "@/components/ui/ui";
import { useAction, useAsync } from "@/hooks/useAsync";
import type { Trade, TradesStats, TradeSort } from "@/types/models";
import { formatDate, formatDays, formatMoney, formatMonth, formatPercent, plural } from "@/utils/format";

import styles from "./TradesPage.module.css";

interface JournalData {
  trades: Trade[];
  stats: TradesStats;
}

const SORTS: ReadonlyArray<{ value: TradeSort; label: string }> = [
  { value: "closed_desc", label: "Сначала новые" },
  { value: "closed_asc", label: "Сначала старые" },
  { value: "profit_desc", label: "По выгоде ↓" },
  { value: "profit_asc", label: "По выгоде ↑" },
  { value: "roi_desc", label: "По ROI ↓" },
];

export function TradesPage(): ReactNode {
  const [sort, setSort] = useState<TradeSort>("closed_desc");
  const [reloadKey, setReloadKey] = useState(0);

  const { state, reload } = useAsync<JournalData>(async () => {
    const [trades, stats] = await Promise.all([fetchTrades(sort), fetchTradesStats()]);
    return { trades, stats };
  }, [sort, reloadKey]);

  const remove = useAction(deleteTrade);

  const handleDelete = async (trade: Trade): Promise<void> => {
    if (!window.confirm(`Удалить сделку «${trade.title}»? Действие необратимо.`)) {
      return;
    }
    const removedId = await remove.run(trade.id);
    // deleteTrade возвращает id удалённой записи; null означает ошибку.
    if (removedId !== null) {
      setReloadKey((value) => value + 1);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Личный журнал"
        title="История сделок"
        subtitle="Закрытые сделки с расчётом выгоды. Показатели считаются по тем же формулам, что и в калькуляторе."
        actions={
          <Link to="/calculator" className={styles.cta}>
            Новая сделка
          </Link>
        }
      />

      <AsyncView
        state={state}
        onRetry={reload}
        loadingText="Читаю журнал сделок…"
        isEmpty={(data) => data.trades.length === 0 && data.stats.trades_count === 0}
        emptyText="Журнал пуст"
        emptyHint="Посчитайте выгоду в калькуляторе и сохраните первую сделку — здесь появится статистика."
      >
        {({ trades, stats }) => (
          <>
            <div className={styles.stats}>
              <StatCard
                label="Итого выгода"
                value={`${stats.total_profit > 0 ? "+" : ""}${formatMoney(stats.total_profit)} ₽`}
                tone={stats.total_profit >= 0 ? "positive" : "negative"}
                hint={`${stats.trades_count} ${plural(stats.trades_count, ["сделка", "сделки", "сделок"])}`}
              />
              <StatCard
                label="ROI портфеля"
                value={formatPercent(stats.roi_pct)}
                tone={stats.roi_pct >= 0 ? "positive" : "negative"}
                hint={`вложено ${formatMoney(stats.total_cost)} ₽`}
              />
              <StatCard
                label="Винрейт"
                value={`${stats.win_rate_pct.toFixed(0)}%`}
                hint={`${stats.profitable_count} в плюс · ${stats.losing_count} в минус`}
              />
              <StatCard
                label="Выгода в день"
                value={`${formatMoney(stats.profit_per_day)} ₽`}
                hint={`средний срок ${formatDays(stats.avg_holding_days)}`}
              />
            </div>

            <div className={styles.panels}>
              <section className={styles.panel}>
                <div className={styles.panelHead}>
                  <h2 className={styles.panelTitle}>Выгода по месяцам</h2>
                  <Badge tone="neutral">{stats.by_month.length} мес</Badge>
                </div>
                <div className={styles.panelBody}>
                  <MonthBars data={stats.by_month} formatLabel={formatMonth} />
                </div>
              </section>

              <section className={styles.panel}>
                <div className={styles.panelHead}>
                  <h2 className={styles.panelTitle}>Самые прибыльные предметы</h2>
                </div>
                <div className={styles.panelBody}>
                  {stats.top_items.length === 0 ? (
                    <p className={styles.emptySmall}>Нет данных</p>
                  ) : (
                    <ol className={styles.topList}>
                      {stats.top_items.map((item) => (
                        <li key={item.item_id}>
                          <span className={styles.topName} title={item.title}>
                            {item.title || item.item_id}
                          </span>
                          <span className={styles.topCount}>{item.trades}×</span>
                          <ProfitValue value={item.profit} size="sm" />
                        </li>
                      ))}
                    </ol>
                  )}
                </div>
              </section>
            </div>

            <div className={styles.tableHead}>
              <h2 className={styles.panelTitle}>Все сделки</h2>
              <label className={styles.sortField}>
                <span className={styles.sortLabel}>Сортировка</span>
                <select
                  className={styles.sortSelect}
                  value={sort}
                  onChange={(event) => setSort(event.target.value as TradeSort)}
                >
                  {SORTS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Предмет</th>
                    <th>Закрыта</th>
                    <th>Срок</th>
                    <th className={styles.right}>Вложено</th>
                    <th className={styles.right}>Выгода</th>
                    <th className={styles.right}>ROI</th>
                    <th aria-label="Действия" />
                  </tr>
                </thead>
                <tbody>
                  {trades.map((trade) => (
                    <tr key={trade.id}>
                      <td>
                        <Link to={`/trades/${trade.id}`} className={styles.tradeLink}>
                          {trade.title || trade.item_id}
                        </Link>
                        {trade.note && <span className={styles.note}>{trade.note}</span>}
                      </td>
                      <td className="num">{formatDate(trade.closed_at)}</td>
                      <td className="num">{formatDays(trade.holding_days)}</td>
                      <td className={`${styles.right} num`}>{formatMoney(trade.cost)} ₽</td>
                      <td className={styles.right}>
                        <ProfitValue value={trade.profit} size="sm" />
                      </td>
                      <td className={styles.right}>
                        <span className={trade.roi_pct >= 0 ? styles.roiUp : styles.roiDown}>
                          {formatPercent(trade.roi_pct)}
                        </span>
                      </td>
                      <td className={styles.right}>
                        <button
                          type="button"
                          className={styles.delete}
                          disabled={remove.state.status === "loading"}
                          onClick={() => void handleDelete(trade)}
                          title="Удалить сделку"
                        >
                          ✕
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {remove.state.status === "error" && (
              <div className={styles.deleteError} role="alert">
                {remove.state.message}
              </div>
            )}
          </>
        )}
      </AsyncView>
    </>
  );
}
