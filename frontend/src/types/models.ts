/**
 * Типы данных фронтенда.
 *
 * Один в один повторяют Pydantic-схемы бэкенда (backend/models/schemas.py):
 * любое расхождение в имени поля ловится компилятором TypeScript, а не
 * выясняется в рантайме. Имена полей намеренно оставлены в snake_case —
 * это ровно то, что отдаёт API, без слоя переименований.
 */

export interface User {
  username: string;
  display_name: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: User;
}

export interface LoginPayload {
  username: string;
  password: string;
}

/* ------------------------------- Рынок -------------------------------- */

export type Verdict = "buy" | "watch" | "skip";

export interface Quote {
  buy_price: number;
  sell_target: number;
  net_sell: number;
  fee_pct: number;
  margin_pct: number;
  margin_abs: number;
  median_price: number;
  p25_price: number;
  p75_price: number;
  lots_count: number;
  competition: number;
  sales_per_day: number;
  liquidity_score: number;
  verdict: Verdict;
  quality: number;
  quality_label: string;
  level: number;
}

export interface Deal {
  item_id: string;
  title: string;
  category: string;
  group: string;
  icon_url: string;
  quality: number;
  quality_label: string;
  level: number;
  level_label: string;
  quote: Quote;
  updated_at: string | null;
  stale_seconds: number | null;
}

export interface Lot {
  lot_id: string;
  amount: number;
  total_price: number;
  unit_price: number;
  end_time: string | null;
}

export interface PricePoint {
  ts: string;
  median_price: number;
  buy_price: number;
  sell_target: number;
  lots_count: number;
}

export interface WatchItem {
  id: number;
  item_id: string;
  title: string;
  category: string;
  icon_url: string;
  enabled: boolean;
  priority: number;
}

export interface ItemDetail {
  item: WatchItem;
  quote: Quote | null;
  lots: Lot[];
  history: PricePoint[];
  updated_at: string | null;
}

/* ------------------------------ Каталог ------------------------------- */

export interface CatalogItem {
  id: string;
  title: string;
  category: string;
  group: string;
  subgroup: string;
  base_price: number;
  price_min: number;
  liquidity: number;
  icon_url: string;
  tracked: boolean;
  estimated: boolean;
  tier_kind: string;
  tier_label: string;
  tier_value: number;
  tier_estimated: boolean;
}

export interface CatalogPage {
  items: CatalogItem[];
  total: number;
  offset: number;
  limit: number;
  tracked_total: number;
  catalog_total: number;
}

export interface CatalogGroup {
  group: string;
  count: number;
}

/** Значения совпадают с Literal в backend/routers/catalog.py. */
export type CatalogSort =
  | "default"
  | "title"
  | "price_desc"
  | "price_asc"
  | "tier_asc"
  | "tier_desc";

export interface CatalogQuery {
  search?: string;
  group?: string;
  tier?: number | null;
  sort?: CatalogSort;
  offset?: number;
  limit?: number;
}

/* ---------------------------- Журнал сделок --------------------------- */

/** Результат расчёта выгоды — общий для калькулятора и журнала. */
export interface TradeMath {
  quantity: number;
  buy_price: number;
  sell_price: number;
  fee_pct: number;
  extra_cost: number;
  cost: number;
  gross_revenue: number;
  fee: number;
  net_revenue: number;
  profit: number;
  roi_pct: number;
  holding_days: number;
  profit_per_day: number;
  is_profitable: boolean;
}

export interface Trade extends TradeMath {
  id: number;
  item_id: string;
  title: string;
  note: string;
  opened_at: string;
  closed_at: string;
}

/** Вход калькулятора: то, что уходит в POST /trades/calculate. */
export interface CalcPayload {
  quantity: number;
  buy_price: number;
  sell_price: number;
  fee_pct: number;
  extra_cost: number;
  opened_at?: string;
  closed_at?: string;
}

/** Сохранение сделки: расчёт плюс предмет и заметка. */
export interface TradePayload extends CalcPayload {
  item_id: string;
  title: string;
  note: string;
}

export interface MonthProfit {
  month: string;
  profit: number;
  trades: number;
}

export interface ItemProfit {
  item_id: string;
  title: string;
  profit: number;
  trades: number;
}

export interface TradesStats {
  trades_count: number;
  profitable_count: number;
  losing_count: number;
  total_cost: number;
  total_revenue: number;
  total_profit: number;
  roi_pct: number;
  win_rate_pct: number;
  best_profit: number;
  worst_profit: number;
  avg_profit: number;
  avg_roi_pct: number;
  avg_holding_days: number;
  profit_per_day: number;
  by_month: MonthProfit[];
  top_items: ItemProfit[];
}

export type TradeSort =
  | "closed_desc"
  | "closed_asc"
  | "profit_desc"
  | "profit_asc"
  | "roi_desc";
