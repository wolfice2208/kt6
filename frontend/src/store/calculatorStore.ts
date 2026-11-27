/**
 * Zustand-хранилище калькулятора выгоды.
 *
 * Здесь только ввод пользователя — сами расчёты делает бэкенд
 * (POST /trades/calculate), поэтому формула существует в одном месте.
 * Значения полей хранятся строками: так поле может быть пустым во время
 * набора, а приведение к числу происходит на выходе (toCalcPayload).
 */

import { create } from "zustand";

import type { CalcPayload } from "@/types/models";

export type CalculatorField =
  | "quantity"
  | "buyPrice"
  | "sellPrice"
  | "feePct"
  | "extraCost"
  | "openedAt"
  | "closedAt";

interface CalculatorState {
  itemId: string;
  itemTitle: string;

  quantity: string;
  buyPrice: string;
  sellPrice: string;
  feePct: string;
  extraCost: string;
  openedAt: string;
  closedAt: string;

  setField: (field: CalculatorField, value: string) => void;
  /** Подставляет предмет и цену из карточки: «посчитать выгоду по этому лоту». */
  prefill: (input: { itemId: string; title: string; buyPrice: number; sellPrice: number }) => void;
  reset: () => void;
}

/** Дата в формате <input type="date"> (YYYY-MM-DD), со сдвигом в прошлое. */
function dateInput(daysAgo = 0): string {
  const date = new Date();
  date.setDate(date.getDate() - daysAgo);
  return date.toISOString().slice(0, 10);
}

const defaults = () => ({
  itemId: "",
  itemTitle: "",
  quantity: "1",
  buyPrice: "",
  sellPrice: "",
  feePct: "0.05",
  extraCost: "0",
  openedAt: dateInput(7),
  closedAt: dateInput(0),
});

export const useCalculatorStore = create<CalculatorState>()((set) => ({
  ...defaults(),

  setField: (field, value) => set({ [field]: value } as Pick<CalculatorState, CalculatorField>),

  prefill: ({ itemId, title, buyPrice, sellPrice }) =>
    set({
      itemId,
      itemTitle: title,
      quantity: "1",
      buyPrice: String(Math.round(buyPrice)),
      sellPrice: String(Math.round(sellPrice)),
      extraCost: "0",
      openedAt: dateInput(7),
      closedAt: dateInput(0),
    }),

  reset: () => set(defaults()),
}));

/** Безопасное приведение пользовательского ввода к числу. */
export function toNumber(value: string, fallback = 0): number {
  const normalized = value.replace(",", ".").trim();
  if (!normalized) return fallback;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : fallback;
}

/** ISO-строка из значения <input type="date">; пустое значение — undefined. */
export function toIsoDate(value: string): string | undefined {
  if (!value) return undefined;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString();
}

/** Вход для POST /trades/calculate, собранный из состояния формы. */
export function toCalcPayload(state: CalculatorState): CalcPayload {
  return {
    quantity: Math.max(1, Math.round(toNumber(state.quantity, 1))),
    buy_price: Math.max(0, toNumber(state.buyPrice)),
    sell_price: Math.max(0, toNumber(state.sellPrice)),
    fee_pct: Math.min(1, Math.max(0, toNumber(state.feePct, 0.05))),
    extra_cost: Math.max(0, toNumber(state.extraCost)),
    opened_at: toIsoDate(state.openedAt),
    closed_at: toIsoDate(state.closedAt),
  };
}

/** Готова ли форма к отправке (минимально осмысленные значения). */
export function isCalculatorReady(state: CalculatorState): boolean {
  return toNumber(state.buyPrice) > 0 && toNumber(state.sellPrice) > 0;
}
