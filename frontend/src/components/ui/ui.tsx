/**
 * Мелкие презентационные примитивы: заголовок страницы, карточка метрики,
 * знак выгоды и бейдж вердикта. Все используют один модуль стилей — это одна
 * дизайн-шкала, а не случайный набор классов.
 */

import type { ReactNode } from "react";

import { formatMoney, formatPercent, profitTone } from "@/utils/format";
import type { Verdict } from "@/types/models";

import styles from "./ui.module.css";

/* ------------------------------- PageHeader ------------------------------ */

interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}

export function PageHeader({ eyebrow, title, subtitle, actions }: PageHeaderProps): ReactNode {
  return (
    <div className={styles.pageHeader}>
      <div>
        {eyebrow && <div className={styles.eyebrow}>{eyebrow}</div>}
        <h1 className={styles.pageTitle}>{title}</h1>
        {subtitle && <p className={styles.pageSubtitle}>{subtitle}</p>}
      </div>
      {actions && <div className={styles.pageActions}>{actions}</div>}
    </div>
  );
}

/* -------------------------------- StatCard ------------------------------- */

type StatTone = "neutral" | "positive" | "negative" | "warning";

interface StatCardProps {
  label: string;
  value: string;
  hint?: string;
  tone?: StatTone;
}

export function StatCard({ label, value, hint, tone = "neutral" }: StatCardProps): ReactNode {
  return (
    <div className={`${styles.statCard} ${styles[`tone_${tone}`] ?? ""}`}>
      <div className={styles.statLabel}>{label}</div>
      <div className={`${styles.statValue} num`}>{value}</div>
      {hint && <div className={styles.statHint}>{hint}</div>}
    </div>
  );
}

/* ------------------------------- ProfitValue ----------------------------- */

interface ProfitValueProps {
  value: number;
  /** Прибыль в рублях или проценты (ROI). */
  kind?: "money" | "percent";
  size?: "sm" | "md" | "lg";
}

export function ProfitValue({ value, kind = "money", size = "md" }: ProfitValueProps): ReactNode {
  const tone = profitTone(value);
  const text =
    kind === "percent"
      ? formatPercent(value)
      : `${value > 0 ? "+" : value < 0 ? "−" : ""}${formatMoney(Math.abs(value))} \u20BD`;

  return (
    <span className={`${styles.profit} ${styles[`profit_${tone}`] ?? ""} ${styles[`size_${size}`] ?? ""} num`}>
      {text}
    </span>
  );
}

/* --------------------------------- Badge --------------------------------- */

const VERDICT_LABEL: Record<Verdict, string> = {
  buy: "выгодно",
  watch: "наблюдать",
  skip: "пропустить",
};

interface VerdictBadgeProps {
  verdict: Verdict;
}

export function VerdictBadge({ verdict }: VerdictBadgeProps): ReactNode {
  return (
    <span className={`${styles.badge} ${styles[`badge_${verdict}`] ?? ""}`}>{VERDICT_LABEL[verdict]}</span>
  );
}

interface BadgeProps {
  children: ReactNode;
  tone?: "neutral" | "positive" | "negative" | "warning" | "info";
}

export function Badge({ children, tone = "neutral" }: BadgeProps): ReactNode {
  return <span className={`${styles.badge} ${styles[`badge_${tone}`] ?? ""}`}>{children}</span>;
}

/* -------------------------------- MonthBars ------------------------------ */

interface MonthBarsProps {
  data: ReadonlyArray<{ month: string; profit: number; trades: number }>;
  /** Подписи месяцев уже отформатированы вызывающим кодом. */
  formatLabel: (month: string) => string;
}

export function MonthBars({ data, formatLabel }: MonthBarsProps): ReactNode {
  if (data.length === 0) {
    return <div className={styles.barsEmpty}>Нет закрытых сделок — динамике неоткуда взяться</div>;
  }

  const maxAbs = Math.max(...data.map((point) => Math.abs(point.profit)), 1);

  return (
    <div className={styles.bars}>
      {data.map((point) => {
        const width = Math.max(3, (Math.abs(point.profit) / maxAbs) * 100);
        const tone = profitTone(point.profit);
        return (
          <div className={styles.barRow} key={point.month}>
            <span className={styles.barLabel}>{formatLabel(point.month)}</span>
            <div className={styles.barTrack}>
              <div
                className={`${styles.barFill} ${styles[`bar_${tone}`] ?? ""}`}
                style={{ width: `${width}%` }}
                title={`${formatMoney(point.profit)} \u20BD · ${point.trades} сделок`}
              />
            </div>
            <span className={`${styles.barValue} ${styles[`profit_${tone}`] ?? ""} num`}>
              {point.profit > 0 ? "+" : point.profit < 0 ? "−" : ""}
              {formatMoney(Math.abs(point.profit))}
            </span>
          </div>
        );
      })}
    </div>
  );
}
