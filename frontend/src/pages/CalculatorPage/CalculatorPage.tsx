/**
 * Калькулятор выгоды.
 *
 * Ввод живёт в Zustand-хранилище, а расчёт делает бэкенд
 * (POST /trades/calculate) с задержкой 400 мс — формула не дублируется
 * на клиенте, поэтому цифры в калькуляторе и в журнале всегда совпадают.
 * Результат и сохранение проходят через те же loading/error/data.
 */

import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import { calculateTrade, createTrade } from "@/api/endpoints";
import { AsyncView } from "@/components/AsyncView/AsyncView";
import { PageHeader, ProfitValue, StatCard } from "@/components/ui/ui";
import { useAction, useAsync } from "@/hooks/useAsync";
import { useAuthStore, useIsAuthenticated } from "@/store/authStore";
import {
  isCalculatorReady,
  toCalcPayload,
  useCalculatorStore,
  type CalculatorField,
} from "@/store/calculatorStore";
import type { CalcPayload, TradeMath } from "@/types/models";
import { formatDays, formatMoney } from "@/utils/format";

import styles from "./CalculatorPage.module.css";

const DEBOUNCE_MS = 400;

export function CalculatorPage(): ReactNode {
  const navigate = useNavigate();
  const isAuthenticated = useIsAuthenticated();
  const token = useAuthStore((state) => state.token);

  const form = useCalculatorStore();
  const ready = isCalculatorReady(form);

  // Значение формы «замораживается» на время debounce: запрос уходит
  // по зафиксированному снимку, а не по последнему нажатию клавиши.
  const [request, setRequest] = useState<CalcPayload | null>(null);

  const signature = JSON.stringify(toCalcPayload(form));

  useEffect(() => {
    if (!ready) {
      setRequest(null);
      return;
    }
    const timer = window.setTimeout(() => {
      setRequest(JSON.parse(signature) as CalcPayload);
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [signature, ready]);

  const save = useAction(createTrade);

  const handleSave = async (): Promise<void> => {
    if (!request) return;
    const trade = await save.run({
      ...request,
      item_id: form.itemId || "manual-entry",
      title: form.itemTitle || "Ручной расчёт",
      note: "",
    });
    if (trade) navigate(`/trades/${trade.id}`);
  };

  return (
    <>
      <PageHeader
        eyebrow="Калькулятор"
        title="Сколько останется на руках"
        subtitle="Комиссия аукциона, дополнительные расходы и срок удержания учитываются в одной формуле. Считает сервер — тот же код, что и в журнале сделок."
      />

      <div className={styles.layout}>
        <section className={styles.formCard}>
          <div className={styles.formHead}>
            <h2 className={styles.formTitle}>Параметры сделки</h2>
            <button type="button" className={styles.reset} onClick={form.reset}>
              Сбросить
            </button>
          </div>

          {form.itemTitle && (
            <div className={styles.subject}>
              <span className={styles.subjectLabel}>Предмет</span>
              <span className={styles.subjectTitle}>{form.itemTitle}</span>
              {form.itemId && <span className={styles.subjectId}>{form.itemId}</span>}
            </div>
          )}

          <div className={styles.grid}>
            <Field
              label="Цена покупки, ₽"
              value={form.buyPrice}
              field="buyPrice"
              placeholder="например 18400"
            />
            <Field
              label="Цена продажи, ₽"
              value={form.sellPrice}
              field="sellPrice"
              placeholder="например 27900"
            />
            <Field label="Количество" value={form.quantity} field="quantity" step="1" />
            <Field
              label="Комиссия, доля"
              value={form.feePct}
              field="feePct"
              step="0.01"
              hint="0.05 = 5%"
            />
            <Field
              label="Прочие расходы, ₽"
              value={form.extraCost}
              field="extraCost"
              step="100"
              hint="перевозка, расходники"
            />
            <label className={styles.field}>
              <span className={styles.label}>Дата покупки</span>
              <input
                type="date"
                className={styles.input}
                value={form.openedAt}
                onChange={(event) => form.setField("openedAt", event.target.value)}
              />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>Дата продажи</span>
              <input
                type="date"
                className={styles.input}
                value={form.closedAt}
                onChange={(event) => form.setField("closedAt", event.target.value)}
              />
            </label>
          </div>

          <div className={styles.saveRow}>
            {isAuthenticated ? (
              <button
                type="button"
                className={styles.save}
                disabled={!ready || save.state.status === "loading"}
                onClick={() => void handleSave()}
              >
                {save.state.status === "loading" ? "Сохраняю…" : "Сохранить в журнал"}
              </button>
            ) : (
              <Link to="/login" state={{ from: "/calculator" }} className={styles.loginPrompt}>
                Войти, чтобы сохранить сделку
              </Link>
            )}
            <span className={styles.saveHint}>
              {token
                ? "Сделка попадёт в ваш личный журнал"
                : "Рынок и калькулятор доступны без входа"}
            </span>
          </div>

          {save.state.status === "error" && (
            <div className={styles.saveError} role="alert">
              {save.state.message}
            </div>
          )}
        </section>

        <section className={styles.resultCard}>
          <h2 className={styles.resultTitle}>Результат</h2>

          {!ready ? (
            <p className={styles.placeholder}>
              Заполните цену покупки и цену продажи — расчёт появится автоматически.
            </p>
          ) : request === null ? (
            <p className={styles.placeholder}>Готовлю расчёт…</p>
          ) : (
            <CalculationView payload={request} />
          )}
        </section>
      </div>
    </>
  );
}

/* ------------------------- поле ввода с подписью ------------------------- */

interface FieldProps {
  label: string;
  value: string;
  field: CalculatorField;
  step?: string;
  placeholder?: string;
  hint?: string;
}

function Field({ label, value, field, step = "1", placeholder, hint }: FieldProps): ReactNode {
  const setField = useCalculatorStore((state) => state.setField);
  return (
    <label className={styles.field}>
      <span className={styles.label}>{label}</span>
      <input
        type="number"
        min="0"
        step={step}
        inputMode="decimal"
        className={styles.input}
        value={value}
        placeholder={placeholder}
        onChange={(event) => setField(field, event.target.value)}
      />
      {hint && <span className={styles.hint}>{hint}</span>}
    </label>
  );
}

/* -------------------------- панель результата ---------------------------- */

function CalculationView({ payload }: { payload: CalcPayload }): ReactNode {
  const { state, reload } = useAsync<TradeMath>(() => calculateTrade(payload), [payload]);

  return (
    <AsyncView state={state} onRetry={reload} loadingText="Считаю на сервере…">
      {(math) => (
        <div className={styles.result}>
          <div className={`${styles.profitBlock} ${math.profit >= 0 ? styles.profitUp : styles.profitDown}`}>
            <span className={styles.profitLabel}>Чистая выгода</span>
            <ProfitValue value={math.profit} size="lg" />
            <span className={styles.roi}>
              ROI <ProfitValue value={math.roi_pct} kind="percent" size="sm" />
            </span>
          </div>

          <div className={styles.miniStats}>
            <StatCard label="Себестоимость" value={`${formatMoney(math.cost)} ₽`} />
            <StatCard label="Выручка" value={`${formatMoney(math.gross_revenue)} ₽`} hint={`комиссия ${formatMoney(math.fee)} ₽`} />
            <StatCard label="На руках" value={`${formatMoney(math.net_revenue)} ₽`} />
            <StatCard
              label="Срок"
              value={formatDays(math.holding_days)}
              hint={`${formatMoney(math.profit_per_day)} ₽/день`}
            />
          </div>

          <dl className={styles.breakdown}>
            <div>
              <dt>
                {math.quantity} × {formatMoney(math.buy_price)} ₽ + расходы {formatMoney(math.extra_cost)} ₽
              </dt>
              <dd className="num">−{formatMoney(math.cost)} ₽</dd>
            </div>
            <div>
              <dt>
                {math.quantity} × {formatMoney(math.sell_price)} ₽
              </dt>
              <dd className="num">+{formatMoney(math.gross_revenue)} ₽</dd>
            </div>
            <div>
              <dt>Комиссия аукциона {(math.fee_pct * 100).toFixed(1)}%</dt>
              <dd className="num">−{formatMoney(math.fee)} ₽</dd>
            </div>
            <div className={styles.total}>
              <dt>Итого выгода</dt>
              <dd>
                <ProfitValue value={math.profit} />
              </dd>
            </div>
          </dl>

          <p className={styles.note}>
            {math.is_profitable
              ? "Сделка прибыльная. Сохраните её в журнал, чтобы она попала в статистику."
              : "При таких ценах сделка убыточная — проверьте цену продажи или расходы."}
          </p>
        </div>
      )}
    </AsyncView>
  );
}
