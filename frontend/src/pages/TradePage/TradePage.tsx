/**
 * Карточка сделки — динамический защищённый маршрут /trades/:tradeId.
 *
 * Параметр приходит строкой, поэтому приводится к числу с проверкой:
 * на /trades/abc страница показывает понятное сообщение, а не падает и
 * не отправляет NaN в API.
 */

import type { ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { deleteTrade, fetchTrade } from "@/api/endpoints";
import { AsyncView } from "@/components/AsyncView/AsyncView";
import { Badge, PageHeader, ProfitValue, StatCard } from "@/components/ui/ui";
import { useAction, useAsync } from "@/hooks/useAsync";
import { useCalculatorStore } from "@/store/calculatorStore";
import type { Trade } from "@/types/models";
import { formatDate, formatDays, formatMoney, formatPercent } from "@/utils/format";

import styles from "./TradePage.module.css";

export function TradePage(): ReactNode {
  // Параметр маршрута типизирован; строка проверяется до запроса.
  const { tradeId } = useParams<{ tradeId: string }>();
  const navigate = useNavigate();
  const prefill = useCalculatorStore((state) => state.prefill);

  const numericId = Number(tradeId);
  const isValidId = Number.isInteger(numericId) && numericId > 0;

  const { state, reload } = useAsync<Trade>(() => fetchTrade(numericId), [numericId]);
  const remove = useAction(deleteTrade);

  const handleDelete = async (trade: Trade): Promise<void> => {
    if (!window.confirm("Удалить эту сделку? Действие необратимо.")) return;
    const removedId = await remove.run(trade.id);
    if (removedId !== null) navigate("/trades", { replace: true });
  };

  const handleRepeat = (trade: Trade): void => {
    prefill({
      itemId: trade.item_id,
      title: trade.title,
      buyPrice: trade.buy_price,
      sellPrice: trade.sell_price,
    });
    navigate("/calculator");
  };

  if (!isValidId) {
    return (
      <>
        <PageHeader eyebrow="Сделка" title="Некорректный номер" />
        <p className={styles.invalid}>
          В адресе ожидалось число, получено «{tradeId}». <Link to="/trades">Вернуться в журнал</Link>
        </p>
      </>
    );
  }

  return (
    <>
      <div className={styles.breadcrumbs}>
        <Link to="/trades">← Журнал сделок</Link>
        <span>/</span>
        <span className={styles.crumbCurrent}>#{tradeId}</span>
      </div>

      <AsyncView
        state={state}
        onRetry={reload}
        loadingText="Загружаю сделку…"
        emptyText="Сделка не найдена"
        emptyHint="Возможно, она удалена или принадлежит другому пользователю."
      >
        {(trade) => (
          <>
            <PageHeader
              eyebrow={trade.item_id}
              title={trade.title || "Без названия"}
              subtitle={`Куплено ${formatDate(trade.opened_at)}, продано ${formatDate(trade.closed_at)}. В руках ${formatDays(trade.holding_days)}.`}
              actions={
                <>
                  <button type="button" className={styles.secondary} onClick={() => handleRepeat(trade)}>
                    Посчитать похожую
                  </button>
                  <button
                    type="button"
                    className={styles.danger}
                    disabled={remove.state.status === "loading"}
                    onClick={() => void handleDelete(trade)}
                  >
                    Удалить
                  </button>
                </>
              }
            />

            <div className={styles.hero}>
              <div className={styles.heroMain}>
                <span className={styles.heroLabel}>Выгода по сделке</span>
                <ProfitValue value={trade.profit} size="lg" />
                <div className={styles.heroMeta}>
                  <Badge tone={trade.is_profitable ? "positive" : "negative"}>
                    ROI {formatPercent(trade.roi_pct)}
                  </Badge>
                  <Badge tone="neutral">{formatMoney(trade.profit_per_day)} ₽/день</Badge>
                </div>
              </div>
              <div className={styles.heroStats}>
                <StatCard label="Вложено" value={`${formatMoney(trade.cost)} ₽`} />
                <StatCard label="Выручка" value={`${formatMoney(trade.gross_revenue)} ₽`} hint={`в том числе комиссия ${formatMoney(trade.fee)} ₽`} />
                <StatCard label="На руках" value={`${formatMoney(trade.net_revenue)} ₽`} />
              </div>
            </div>

            <div className={styles.columns}>
              <section className={styles.panel}>
                <div className={styles.panelHead}>
                  <h2 className={styles.panelTitle}>Расчёт</h2>
                </div>
                <dl className={styles.rows}>
                  <div>
                    <dt>Количество</dt>
                    <dd className="num">{trade.quantity}</dd>
                  </div>
                  <div>
                    <dt>Цена покупки за единицу</dt>
                    <dd className="num">{formatMoney(trade.buy_price)} ₽</dd>
                  </div>
                  <div>
                    <dt>Цена продажи за единицу</dt>
                    <dd className="num">{formatMoney(trade.sell_price)} ₽</dd>
                  </div>
                  <div>
                    <dt>Комиссия аукциона</dt>
                    <dd className="num">{formatPercent(trade.fee_pct * 100, false)}</dd>
                  </div>
                  <div>
                    <dt>Прочие расходы</dt>
                    <dd className="num">{formatMoney(trade.extra_cost)} ₽</dd>
                  </div>
                  <div className={styles.totalRow}>
                    <dt>Себестоимость</dt>
                    <dd className="num">{formatMoney(trade.cost)} ₽</dd>
                  </div>
                  <div className={styles.totalRow}>
                    <dt>Чистая выручка</dt>
                    <dd className="num">{formatMoney(trade.net_revenue)} ₽</dd>
                  </div>
                </dl>
              </section>

              <section className={styles.panel}>
                <div className={styles.panelHead}>
                  <h2 className={styles.panelTitle}>Детали</h2>
                </div>
                <dl className={styles.rows}>
                  <div>
                    <dt>Предмет</dt>
                    <dd>
                      <Link to={`/catalog/${trade.item_id}`} className={styles.itemLink}>
                        {trade.item_id}
                      </Link>
                    </dd>
                  </div>
                  <div>
                    <dt>Дата покупки</dt>
                    <dd>{formatDate(trade.opened_at)}</dd>
                  </div>
                  <div>
                    <dt>Дата продажи</dt>
                    <dd>{formatDate(trade.closed_at)}</dd>
                  </div>
                  <div>
                    <dt>Срок удержания</dt>
                    <dd>{formatDays(trade.holding_days)}</dd>
                  </div>
                  <div>
                    <dt>Выгода в день</dt>
                    <dd className="num">{formatMoney(trade.profit_per_day)} ₽</dd>
                  </div>
                  <div>
                    <dt>Заметка</dt>
                    <dd>{trade.note || "—"}</dd>
                  </div>
                </dl>
              </section>
            </div>

            {remove.state.status === "error" && (
              <div className={styles.error} role="alert">
                {remove.state.message}
              </div>
            )}
          </>
        )}
      </AsyncView>
    </>
  );
}
