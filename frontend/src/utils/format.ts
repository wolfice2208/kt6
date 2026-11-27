/** Форматирование чисел и дат в одном месте: компоненты не изобретают своё. */

const moneyFormatter = new Intl.NumberFormat("ru-RU", {
  maximumFractionDigits: 0,
});

const compactFormatter = new Intl.NumberFormat("ru-RU", {
  notation: "compact",
  maximumFractionDigits: 1,
});

export function formatMoney(value: number): string {
  return moneyFormatter.format(Math.round(value));
}

export function formatMoneyCompact(value: number): string {
  return compactFormatter.format(value);
}

export function formatPercent(value: number, withSign = true): string {
  const sign = withSign && value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}

export function formatRatio(value: number): string {
  return value.toFixed(2);
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString("ru-RU", { day: "2-digit", month: "short", year: "numeric" });
}

export function formatDateShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });
}

/** «Фев 2026» из «2026-02». */
export function formatMonth(month: string): string {
  const [year, monthPart] = month.split("-");
  const date = new Date(Number(year), Number(monthPart) - 1, 1);
  if (Number.isNaN(date.getTime())) return month;
  return date.toLocaleDateString("ru-RU", { month: "short", year: "numeric" });
}

export function formatDays(value: number): string {
  if (value < 1) return `${Math.round(value * 24)} ч`;
  return `${value.toFixed(1).replace(".", ",")} дн`;
}

/** Русские окончания: 1 сделка, 2 сделки, 5 сделок. */
export function plural(count: number, forms: [string, string, string]): string {
  const abs = Math.abs(count) % 100;
  const last = abs % 10;
  if (abs > 10 && abs < 20) return forms[2];
  if (last > 1 && last < 5) return forms[1];
  if (last === 1) return forms[0];
  return forms[2];
}

/** Класс для окраски прибыли/убытка. */
export function profitTone(value: number): "positive" | "negative" | "neutral" {
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "neutral";
}
