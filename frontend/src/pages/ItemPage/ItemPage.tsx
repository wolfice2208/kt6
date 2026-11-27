/**
 * Карточка предмета — динамический маршрут /catalog/:itemId.
 *
 * Параметр типизирован: useParams<{ itemId: string }>(). Если предмета нет,
 * бэкенд отвечает 404, и это отдельное состояние интерфейса, а не «пустой экран».
 */

import type { ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { fetchItem } from "@/api/endpoints";
import { AsyncView } from "@/components/AsyncView/AsyncView";
import { Badge, PageHeader, StatCard, VerdictBadge } from "@/components/ui/ui";
import { useAsync } from "@/hooks/useAsync";
import { useCalculatorStore } from "@/store/calculatorStore";
import type { ItemDetail, Quote } from "@/types/models";
import { formatDays, formatMoney, formatPercent } from "@/utils/format";

import styles from "./ItemPage.module.css";

export function ItemPage(): ReactNode {
  // Типизированные параметры маршрута: id всегда строка, а не string | undefined.
  const { itemId } = useParams<{ itemId: string }>();
  const navigate = useNavigate();
  const prefill = useCalculatorStore((state) => state.prefill);

  const { state, reload } = useAsync<ItemDetail>(
    () => fetchItem(itemId ?? ""),
    [itemId],
  );

  const handleCalculate = (detail: ItemDetail, quote: Quote): void => {
    prefill({
      itemId: detail.item.item_id,
      title: detail.item.title,
      buyPrice: quote.buy_price,
      sellPrice: quote.net_sell,
    });
    navigate("/calculator");
  };

  return (
    <>
      <div className={styles.breadcrumbs}>
        <Link to="/catalog">← Каталог</Link>
        <span>/</span>
        <span className={styles.crumbCurrent}>{itemId}</span>
      </div>

      <AsyncView
        state={state}
        onRetry={reload}
        loadingText="Загружаю карточку предмета…"
        emptyText="Предмет не найден"
        emptyHint="Возможно, он больше не отслеживается. Вернитесь в каталог."
      >
        {(detail) => {
          const quote = detail.quote;
          // У артефактов качество и прокачка — свойства конкретного лота,
          // поэтому маржа считается внутри класса, а не по всем лотам сразу.
          const isArtefact = detail.item.category.startsWith("artefact/");
          return (
            <>
              <PageHeader
                eyebrow={detail.item.category || "Предмет"}
                title={detail.item.title || detail.item.item_id}
                subtitle={
                  quote
                    ? `Лучший лот ${formatMoney(quote.buy_price)} ₽ · цель продажи ${formatMoney(quote.net_sell)} ₽ после комиссии`
                    : "По этому предмету ещё нет данных рынка"
                }
                actions={
                  quote ? (
                    <button
                      type="button"
                      className={styles.cta}
                      onClick={() => handleCalculate(detail, quote)}
                    >
                      Посчитать выгоду
                    </button>
                  ) : undefined
                }
              />

              {!quote ? (
                <div className={styles.noQuote}>
                  Воркер ещё не собрал лоты по этому предмету. Подождите обхода или обновите
                  страницу.
                </div>
              ) : (
                <>
                  <div className={styles.stats}>
                    <StatCard
                      label="Купить по"
                      value={`${formatMoney(quote.buy_price)} ₽`}
                      hint={
                        isArtefact
                          ? `лучший лот класса «${quote.quality_label || "—"}» +${quote.level}`
                          : "самый дешёвый активный лот"
                      }
                    />
                    <StatCard label="Продать по" value={`${formatMoney(quote.net_sell)} ₽`} hint="за вычетом комиссии" />
                    <StatCard
                      label="Маржа"
                      value={`${formatMoney(quote.margin_abs)} ₽`}
                      hint={formatPercent(quote.margin_pct)}
                      tone={quote.margin_abs > 0 ? "positive" : "negative"}
                    />
                    <StatCard label="Ликвидность" value={`${quote.sales_per_day.toFixed(1)}/сут`} hint={`конкурентов: ${quote.competition}`} />
                  </div>

                  <div className={styles.columns}>
                    <section className={styles.panel}>
                      <div className={styles.panelHead}>
                        <h2 className={styles.panelTitle}>Активные лоты</h2>
                        <Badge tone="info">{detail.lots.length} шт</Badge>
                      </div>
                      {detail.lots.length === 0 ? (
                        <p className={styles.panelEmpty}>Активных лотов нет</p>
                      ) : (
                        <>
                          <p className={styles.panelNote}>
                            {isArtefact
                              ? "Показаны все лоты независимо от качества и прокачки. Цена выкупа в карточке считается по лучшему классу — он выделен в таблице."
                              : "Отсортированы по цене за единицу. Выделен лот, по которому посчитана маржа."}
                          </p>
                          <table className={styles.table}>
                            <thead>
                              <tr>
                                <th>Цена за ед.</th>
                                <th>Количество</th>
                                <th>Итого</th>
                              </tr>
                            </thead>
                            <tbody>
                              {detail.lots.slice(0, 12).map((lot) => (
                                <tr
                                  key={lot.lot_id}
                                  className={
                                    Math.abs(lot.unit_price - quote.buy_price) < 0.01
                                      ? styles.bestLot
                                      : undefined
                                  }
                                >
                                  <td className="num">{formatMoney(lot.unit_price)} ₽</td>
                                  <td className="num">{lot.amount}</td>
                                  <td className="num">{formatMoney(lot.total_price)} ₽</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </>
                      )}
                    </section>

                    <section className={styles.panel}>
                      <div className={styles.panelHead}>
                        <h2 className={styles.panelTitle}>Оценка рынка</h2>
                        <VerdictBadge verdict={quote.verdict} />
                      </div>
                      <dl className={styles.facts}>
                        <div>
                          <dt>Медиана лотов</dt>
                          <dd className="num">{formatMoney(quote.median_price)} ₽</dd>
                        </div>
                        <div>
                          <dt>Перцентиль 25%</dt>
                          <dd className="num">{formatMoney(quote.p25_price)} ₽</dd>
                        </div>
                        <div>
                          <dt>Перцентиль 75%</dt>
                          <dd className="num">{formatMoney(quote.p75_price)} ₽</dd>
                        </div>
                        <div>
                          <dt>Комиссия аукциона</dt>
                          <dd className="num">{formatPercent(quote.fee_pct * 100, false)}</dd>
                        </div>
                        <div>
                          <dt>Качество</dt>
                          <dd>{quote.quality_label || "—"}</dd>
                        </div>
                        <div>
                          <dt>Данные обновлены</dt>
                          <dd>
                            {detail.updated_at
                              ? `${formatDays((Date.now() - new Date(detail.updated_at).getTime()) / 86_400_000)} назад`
                              : "—"}
                          </dd>
                        </div>
                      </dl>
                    </section>
                  </div>
                </>
              )}
            </>
          );
        }}
      </AsyncView>
    </>
  );
}
